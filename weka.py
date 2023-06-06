################################################################################################
# Weka Specific Code
################################################################################################
import curses
import ipaddress
import sys
from collections import OrderedDict
from logging import getLogger

from wekalib import signal_handling
from wekalib.exceptions import LoginError, CommunicationError, NewConnectionError
from wekalib.wekaapi import WekaApi
from wekapyutils.sthreads import default_threader
from wekapyutils.wekassh import RemoteServer, parallel, threaded_method

log = getLogger(__name__)


def shutdown_curses(opaque):
    try:
        curses.echo()
        curses.nocbreak()
        curses.endwin()
    except:
        pass


signal_handler = signal_handling(graceful_terminate=shutdown_curses)


class WekaInterface(ipaddress.IPv4Interface):
    def __init__(self, linklayer, name, address, speed):
        self.type = linklayer
        self.name = name
        self.speed = speed
        self.gateway = None
        super(WekaInterface, self).__init__(address)


class STEMHost(object):
    # uses ONLY the API...
    def __init__(self, name):
        self.name = name
        self.host_api = None
        self.machine_info = None
        self.ssh_client = None
        self.hyperthread = None
        self.lscpu_data = None
        self.drives = dict()
        self.drive_devs = dict()
        self.nics = dict()
        self.cpu_model = None
        self.num_cores = None
        self.dataplane_nics = dict()
        self.total_ramGB = None
        self.version = None

    def get_machine_info(self):
        """
        get the info_hw output from the API
        """
        try:
            self.machine_info = self.host_api.weka_api_command("machine_query_info", parms={})
        except LoginError:
            log.info(f"host {self.name} failed login querying info")
            return
        except CommunicationError:
            log.info(f"Error communicating with host {self.name} querying info")
            return

        self.num_cores = len(self.machine_info['cores'])
        self.cpu_model = self.machine_info['cores'][0]['model']
        self.version = self.machine_info['version']
        # self.info_hw = info_hw  # save a copy in case we need it
        self.total_ramGB = int(self.machine_info["memory"]["total"] / 1024 / 1024 / 1024)

        for drive in self.machine_info['disks']:
            if drive['type'] == "DISK" and not drive['isRotational'] and not drive['isMounted'] and \
                    len(drive['pciAddr']) > 0 and drive['type'] == 'DISK':
                # not drive['isSwap'] and \     # pukes now; no longer there in 3.13
                # self.drives[drive['devName']] = drive['devPath']
                self.drives[drive['devName']] = drive

        # need to determine if any of the above drives are actually in use - boot devices, root drives, etc.
        # how?
        #                 "parentName": "sda",
        #                 "type": "PARTITION",
        #                 "isMounted": true,

        # remove any drives with mounted partitions from the list
        for drive in self.machine_info['disks']:
            if drive['type'] == "PARTITION" and drive['parentName'] in self.drives and drive['isMounted']:
                # if drive['isSwap'] or drive['isMounted']:
                del self.drives[drive['parentName']]

        for net_adapter in self.machine_info['net']['interfaces']:
            if net_adapter['name'] == 'lo':  # we can't use loopback interfaces anyway
                continue
            # (bruce) change lowest allowed mtu to 1400 - we technically support 2k on ib
            # and in theory support 1500 on eth, so don't abort without options for low MTUs
            if net_adapter['mtu'] <= 1400 or net_adapter['mtu'] >= 10000:
                log.debug(
                    f'{self.name}: Skipping {net_adapter["name"]} due to MTU {net_adapter["mtu"]} out of range')
                continue
            if len(net_adapter['ip4']) <= 0:
                log.debug(f'{self.name}: Skipping interface {net_adapter["name"]} - unconfigured')
                continue

            if net_adapter['bondType'] == 'SLAVE':
                log.debug(f'{self.name}: Skipping interface {net_adapter["name"]} - is a slave to a bond')
                continue

            if net_adapter['bondType'] == 'NONE':  # "NONE", "BOND" and "SLAVE" are valid
                # a "regular" interface
                details = self.find_interface_details(net_adapter['name'])
                if details is None:
                    log.error(f"no details available for {net_adapter['name']} on host '{self.name}' - skipping")
                    continue
                if details['validationCode'] == "OK" and details['linkDetected']:
                    self.nics[net_adapter['name']] = WekaInterface(net_adapter['linkLayer'],
                                                                   net_adapter['name'],
                                                                   f"{net_adapter['ip4']}/{net_adapter['ip4Netmask']}",
                                                                   details['speedMbps'])
                    log.info(f"{self.name}: interface {net_adapter['name']} added to config")
            elif net_adapter['bondType'][:4] == 'BOND':  # can be "BOND_MLTI_NIC" or whatever.  Same diff to us
                # bonds don't appear in the net_adapters... have to build it from the slaves
                if len(net_adapter['name_slaves']) == 0:  # what are other values?
                    log.error(f"{self.name}:{net_adapter['name']}: bond has no slaves?; skipping")
                    continue
                log.info(f"{self.name}:{net_adapter['name']}:name_slaves = {net_adapter['name_slaves']}")
                # find an "up" slave, if any
                for slave in net_adapter['name_slaves']:
                    details = self.find_interface_details(slave)
                    if details is None:
                        log.error(f"no details available for {slave} on host '{self.name}' - skipping")
                        continue
                    if details['validationCode'] == "OK" and details['linkDetected']:
                        log.info(f"{self.name}: {net_adapter['name']}: slave {details['ethName']} good.")
                        self.nics[net_adapter['name']] = \
                            WekaInterface(net_adapter['linkLayer'], net_adapter['name'],
                                          f"{net_adapter['ip4']}/{net_adapter['ip4Netmask']}", details['speedMbps'])
                        log.info(f"{self.name}: bond {net_adapter['name']} added to config")
                        # we don't care about other slaves once we find a working one - they should all be the same
                        break
                log.error(f"{self.name}: bond {net_adapter['name']} has no up slaves - skipping")
            else:
                log.info(f"{self.name}:{net_adapter['name']} - unknown bond type {net_adapter['bondType']}")

    def find_interface_details(self, iface):
        for eth in self.machine_info['eths']:
            if eth['interface_alias'] == iface:
                return eth
        return None

    #    def find_bond_details(self, iface):
    #        for eth in self.machine_info['eths']:
    #            if eth['ethBondingMaster'] == iface:
    #                return eth
    #        return None

    def __str__(self):
        return self.name

    def open_api(self, ip_list=None):
        """
        Try to open a connection to the API on the host; try all listed IPs, take first one that works
        depending on how we're running, we may or may not be able to talk to the host over every ip...

        :param ip_list: a list of ip addrs
        :return: weka api object
        """
        if ip_list is None:
            ip_list = [self.name]

        log.debug(f"host {self.name}: {ip_list}")
        ip = None
        for ip in ip_list:
            try:
                log.debug(f"{self.name}: trying on {ip}")
                self.host_api = WekaApi(ip, scheme="http", verify_cert=False, timeout=5)
                break
            except LoginError:
                log.debug(f"host {self.name} failed login on ip {ip}?")
                continue
            except CommunicationError as exc:
                log.debug(f"Error opening API for host {self.name} on ip {ip}: {exc}")
                continue
            except NewConnectionError as exc:
                log.error(f"Unable to contact host {self.name} - is weka installed there?")
                continue
            except Exception as exc:
                log.error(f"Other exception on host {self.name}: {exc}")
                continue

        if self.host_api is None:
            log.debug(f"{self.name}: unable to open api to {self.name}")
            return None
        else:
            log.debug(f"host api opened on {self.name} via {ip}")


class WekaHostGroup():
    def __init__(self, reference_hostname, beacons):
        """
        This routine is run before the TUI starts to scope out the cluster.

        Using reference_hostname as a basis, find the other hosts that we can make into a cluster
        The idea is to narrow down the beacons list to something that will work
        Then analyze the hosts (networks and whatnot) to see how we can configure things

        :param reference_hostname: hostname of the starter host (given on command line)
        :param beacons: dict of hostname:[list of ip addrs]
        :return: a list of STEMHost objects
        """
        self.isrouted = False
        self.one_network = False
        self.usable_hosts = dict()
        self.accessible_hosts = dict()  # a dict of {ifname:(hostname)}  (set of hostnames on the nic)
        self.pingable_ips = dict()
        self.numnets = dict()

        default_threader.num_simultaneous = 5  # ssh has a default limit of 10 sessions at a time
        self.beacons = beacons
        if reference_hostname == "localhost":
            import platform
            self.reference_hostname = platform.node()
            ref_is_local = True  # note that we don't need to use ssh to run commands here
        else:
            self.reference_hostname = reference_hostname  # for now
            ref_is_local = False  # note that we DO need to use ssh to run commands on this host

        candidates = dict()
        # cycle through the beacon hosts, and fetch their HW info, create STEMHosts
        log.info(f"Getting configuration info from hosts...")
        for host, ip_list in self.beacons.items():
            # if we're going to do this, we have to create the STEMHost object first, not below
            candidate = STEMHost(host)
            # Open an API to each host, in parallel
            log.info(f"opening api to {host}")
            threaded_method(candidate, STEMHost.open_api, ip_list)  # schedule to run (they're slow)
            candidates[host] = candidate
            # candidate.open_api(ip_list)

        default_threader.run()  # run the threaded methods

        # weed out the ones we can't talk to or reach
        for host, candidate in candidates.copy().items():
            if candidate.host_api is None:
                log.info(f"Unable to communicate with {host} - skipping")
                del candidates[host]  # remove it from the list

        parallel(candidates.values(), STEMHost.get_machine_info)

        # find the basis host (the one they gave us on the command line)
        if self.reference_hostname not in candidates:
            # something is amiss - the host they told us to talk to doesn't list itself as a STEM host?
            log.error(f"{self.reference_hostname}: Unable to fetch HW info from reference host (self); aborting")
            log.error("This is normally due to ssh issues")
            sys.exit(1)

        self.referencehost_obj = candidates[self.reference_hostname]

        if len(self.referencehost_obj.nics) == 0:
            log.error(f"Reference host ({self.referencehost_obj.name}) has no usable nics?")
            sys.exit(1)

        # find hosts that can cluster with reference_hostname - they pointed us at reference_hostname for a reason
        log.info(f"Reference Host {self.reference_hostname} is running WEKA release {self.referencehost_obj.version}")
        log.info(f"Searching for other {self.referencehost_obj.version} hosts...")
        for host, candidate in candidates.copy().items():  # copy it so we can del() from orig list
            if candidate.machine_info is None:
                log.error(f"Error communicating with {host} - removing from list")
                del candidates[host]  # remove it from the list
            if candidate.version != self.referencehost_obj.version:
                log.info(f"    host {host} is not running v{self.referencehost_obj.version} - removing from list")
                del candidates[host]
                continue
            log.info(f"Host {host} added to list of cluster hosts")

        log.info("Preparing to explore network...")
        self.ssh_client = RemoteServer(self.reference_hostname)
        self.ssh_client.connect()

        # not sure this is still needed - can't be none or connect() above would crash
        # if self.ssh_client is None:
        #    log.error(f"ERROR: unable to ssh to {self.reference_hostname}")
        #    sys.exit(1)

        # make sure reference_hostname can talk to the others over the dataplane networks; narrow the list,
        # and collect details of what weka hosts we can see on each nic
        # self.accessible_hosts = dict()  # a dict of {ifname:(hostname)}  (set of hostnames on the nic)
        # self.pingable_ips = dict()
        # self.numnets = dict()
        for source_interface in self.referencehost_obj.nics.keys():
            self.accessible_hosts[source_interface] = set()  # hosts by interface on the reference host
            self.accessible_hosts[source_interface].add(self.reference_hostname)  # always add this
            self.pingable_ips[source_interface] = list()  # ips pingable from this interface
            self.numnets[source_interface] = set()

        log.info("Exploring network... this may take a while")
        # set up for parallel execution
        log.debug(f"refhost.nics = {list(self.referencehost_obj.nics.keys())}")
        for hostname, hostobj in candidates.items():
            log.info(f'Looking at host {hostname}...')
            # see if the reference host can talk to the target ip on each interface
            for source_interface in self.referencehost_obj.nics.keys():  # refhost nic
                for targetif, targetip in hostobj.nics.items():  # candidate nic
                    if hostname == reference_hostname and source_interface == targetif:
                        self.pingable_ips[source_interface].append(targetip)  # make sure refhost is there
                        continue  # not sure why, but ping fails on loopback anyway

                    log.debug(f"checking {hostobj.name}/{source_interface}/{targetip.ip} from {source_interface}")
                    threaded_method(self, WekaHostGroup.ping_clients, source_interface, hostobj, targetip)

        # execute them
        default_threader.run()

        # merge the accessible_hosts sets - we need the superset for later
        usable_set = set()  # should we really be using sets here?  A dict might work easier
        # self.usable_hosts = dict()  # definitive list (well, dict) of hosts
        for host_set in self.accessible_hosts.values():
            if len(usable_set) != 0 and host_set != usable_set:
                log.warning("Not all hosts are accessible from all interfaces - check network config")
            usable_set = usable_set.union(host_set)
        # log.info(f"There are {len(usable_set)} ping-able hosts")
        for host in usable_set:
            self.usable_hosts[host] = candidates[host]
        # for some odd reason, the above ping doesn't work when loopback.  Go figure
        self.usable_hosts[self.referencehost_obj.name] = self.referencehost_obj  # he gets left out

        log.info(f"There appear to be {len(self.usable_hosts)} usable hosts - {sorted(list(self.usable_hosts.keys()))}")

        # are the other hosts on different subnets?
        for source_interface in self.referencehost_obj.nics.keys():
            if len(self.numnets[source_interface]) > 1:
                self.isrouted = True  # not completely sure this is correct...

        # is there more than one subnet on this host? (ie: are all the interfaces on the same subnet?)
        if not self.isrouted:
            self.local_subnets = []
            for source_interface, if_obj in self.referencehost_obj.nics.items():
                if if_obj.network not in self.local_subnets:
                    self.local_subnets.append(if_obj.network)
            if len(self.local_subnets) > 1:
                self.isrouted = True  # hmm... doesn't really mean it's routed; could be just 2 subnets
            else:
                self.one_network = True

        # network link layer types
        self.link_types = list()
        for source_interface, if_obj in self.referencehost_obj.nics.items():
            if if_obj.type not in self.link_types:
                self.link_types.append(if_obj.type)

        # do we have both IB and ETH interfaces? (maybe we should check this AFTER they select the dataplane?)
        if len(self.link_types) > 1:
            self.mixed_networking = True
        else:
            self.mixed_networking = False

        # go probe the hosts to see if they have a default route set, if so, we'll config weka to use it
        log.info(f"Opening ssh to hosts")
        self.open_ssh_toall()

        # default_threader.num_simultaneous = 5  # ssh has a default limit of 10 sessions at a time
        log.info("Probing for gateways")
        for host, host_obj in sorted(self.usable_hosts.items()):
            for nicname, nic_obj in host_obj.nics.items():
                # threaded_method(host_obj, WekaHostGroup.get_gateways, host_obj, nic_obj)
                if nic_obj.type != "IB":  # we don't support gateways on IB
                    self.get_gateways(host_obj, nic_obj)
        # parallel(self, WekaHostGroup.get_gateways)
        # default_threader.run()
        self.get_hostinfo()

    def ping_clients(self, source_interface, hostobj, targetip):
        hostname = hostobj.name
        log.debug(f"pinging from {hostname}/{source_interface} to {targetip.ip}")
        # Note that self.ssh_client is a session open to refhost...
        ssh_out = self.ssh_client.run(f"ping -c1 -W1 -I {source_interface} {targetip.ip}")
        if ssh_out.status == 0:
            log.debug(f"Ping successful - adding {hostname} to accessible_hosts")
            # we were able to ping the host!  add it to the set of hosts we can access via this IF

            self.accessible_hosts[source_interface].add(hostname)
            self.pingable_ips[source_interface].append(targetip)
            if targetip.network not in self.numnets[source_interface]:
                self.numnets[source_interface].add(targetip.network)  # note unique networks (should get blake's)
        else:
            log.debug(f"From {source_interface} target {hostname}-{targetip} failed with rc={ssh_out.status}")

    def get_gateways(self, host, nic):
        log.info(f"probing gateway for {host}/{nic.name}")

        # try google DNS because we're sure they don't have it on their network...
        if not self.probe_gateway(host, nic, '8.8.8.8'):
            # no default gateway, see if there are any gateways to the other nodes...
            for interface, target in self.pingable_ips.items():
                if not self.probe_gateway(host, nic, target):
                    continue
        if nic.gateway is not None:
            log.info(f"    {host}/{nic.name} has gateway {nic.gateway}")
        else:
            log.warning(f"    {host}/{nic.name} has no gateway")
        return  # gateway is set in nic, if it was found

    def probe_gateway(self, host, nic, target):
        cmd_output = host.ssh_client.run(f"ip route get {target} oif {nic.name}")

        if cmd_output.status == 0:
            outputlines = cmd_output.stdout.split('\n')
            if len(outputlines) > 0:
                splitlines = outputlines[0].split()
                if splitlines[1] == 'via':  # There's a gateway!
                    nic.gateway = splitlines[2]
                    return True
        else:
            log.debug(f"Error executing 'ip route get' on {host}:{nic.name}:" +
                      f" return code={cmd_output.status}," +
                      f" stderr={list(cmd_output.stderr)}")
        return False

    def open_ssh_toall(self):
        self.clients = dict()
        for host, host_obj in self.usable_hosts.items():
            # open sessions to all the hosts
            self.clients[host] = RemoteServer(host)
            self.clients[host].user = self.ssh_client.user
            self.clients[host].password = self.ssh_client.password if self.ssh_client.password is not None else ""
            host_obj.ssh_client = self.clients[host]
        parallel(self.clients.values(), RemoteServer.connect)

    def is_homogeneous(self):
        """
        # check if all the hosts are the same.  Note ones that are different.
        :return:
        """

        cores = dict()  # dict of {numcores: [hosts]}
        hyperthreads = dict()
        ram = dict()  # dict of {ram_GB: [hosts]}
        drives = dict()  # dict of {num_drives: [hosts]}
        drive_sizes = dict()
        homo = True

        # loop through, make notes
        for host, host_obj in self.usable_hosts.items():
            # check cores
            corehostlist = cores.get(host_obj.num_cores, list())
            corehostlist.append(host)
            cores[host_obj.num_cores] = corehostlist

            hyperthreadlist = hyperthreads.get(host_obj.hyperthread, list())
            hyperthreadlist.append(host)
            hyperthreads[host_obj.hyperthread] = hyperthreadlist

            # check RAM
            ramhostlist = ram.get(int(host_obj.total_ramGB), list())
            ramhostlist.append(host)
            ram[int(host_obj.total_ramGB)] = ramhostlist

            # check # of drives - {numdrives: [list of host objects]}
            drivehostlist = drives.get(len(host_obj.drives), list())
            drivehostlist.append(str(host_obj))
            drives[len(host_obj.drives)] = drivehostlist

            # these_drives = drive_sizes.get(host_obj.drives, list())   # returns list of drives
            # find the host_obj.machine_info.disks entry (its a list) where dev_path == these_drives
            for drive in host_obj.drives.values():
                drive_size_hostlist = drive_sizes.get(drive['sizeBytes'], list())
                if host not in drive_size_hostlist:
                    drive_size_hostlist.append(host)
                drive_sizes[drive['sizeBytes']] = drive_size_hostlist

        if len(cores) != 1:
            homo = False
            log.error("Hosts do not have a homogeneous number of cores")
            for corecount, corehostlist in sorted(cores.items()):
                log.info(f"  There are {len(corehostlist)} hosts with {corecount} cores: {sorted(corehostlist)}")

        if len(hyperthreads) != 1:
            log.error("Not all hosts share hyperthread/SMT setting")
            for value, hostlist in hyperthreads.items():
                log.info(f"  There are {len(hostlist)} hosts with Hyperthreading/SMT {value}: {sorted(hostlist)}")

        if len(ram) != 1:
            homo = False
            log.error("Hosts do not have a homogeneous amount of ram")
            for ram_GB, ramhostlist in sorted(ram.items()):
                log.info(f"  There are {len(ramhostlist)} hosts with {ram_GB} GB of RAM: {sorted(ramhostlist)}")

        if len(drives) != 1:
            homo = False
            log.error("Hosts do not have a homogeneous number of drives")
            for num_drives, drivehostlist in sorted(drives.items()):
                log.info(f"  There are {len(drivehostlist)} hosts with {num_drives} drives: {sorted(drivehostlist)}")

        if len(drive_sizes) != 1:
            homo = False
            log.error("Hosts do not have a homogeneous drive sizes")
            for drive_size, drivehostlist in sorted(drive_sizes.items()):
                log.info(f"  There are {len(drivehostlist)} hosts with " +
                         f"{round(drive_size / 1000 / 1000 / 1000 / 1000, 2)} TB/" +
                         f"{round(drive_size / 1024 / 1024 / 1024 / 1024, 2)} TiB " +
                         f"drives: {sorted(drivehostlist)}")

        return homo

    def get_hostinfo(self):
        """
        # get info on the hosts
        :return:
        """
        for host, host_obj in self.usable_hosts.items():
            threaded_method(self, WekaHostGroup.lscpu, host_obj)

        default_threader.run()

        for host, host_obj in self.usable_hosts.items():
            threads = host_obj.lscpu_data.get('Thread(s) per core', '')
            host_obj.hyperthread = False if threads == '1' else True
            host_obj.threads_per_core = int(threads)
            log.debug(f"{host} hyperthreading/SMT is {host_obj.hyperthread}")

        pass

    def lscpu(self, hostobj):
        hostobj.lscpu_data = dict()
        cmd_output = self.ssh_client.run("lscpu")
        if cmd_output.status == 0:
            # we were able to run lscpu
            outputlines = cmd_output.stdout.split('\n')
            if len(outputlines) > 0:
                log.debug(f"got lscpu output for {hostobj.name}")
                for line in outputlines:
                    splitlines = line.split(':')
                    if len(splitlines) > 1:
                        hostobj.lscpu_data[splitlines[0]] = splitlines[1].strip()

        else:
            log.error(f"lscpu failed on {hostobj.name}")


def beacon_hosts(hostname):
    """
    :param hostname: str
    :return: a dict of hostname:[list of ip addrs]
    """
    # start with the hostname given; get a list of beacons from it
    log.info("finding hosts...")
    reference_host = STEMHost(hostname)
    reference_host.open_api([hostname])
    if reference_host.host_api is None:
        log.info(f"ERROR: Unable to contact host '{hostname}'")
        sys.exit(1)  # very hard error

    if not reference_host.host_api.STEMMode:
        log.info(f"host {hostname} is already part of a cluster")
        sys.exit(1)

    # returns a dict of {ipaddr:hostname}
    beacons = reference_host.host_api.weka_api_command("cluster_list_beacons", parms={})

    # make a dict of {hostname:[ipaddr]}
    stem_beacons = dict()
    for ip, hostname in beacons.items():
        if hostname not in stem_beacons:
            stem_beacons[hostname] = [ip]
        else:
            stem_beacons[hostname].append(ip)

    for host, ips in stem_beacons.items():
        log.info(f"{host}: {sorted(ips)}")

    return OrderedDict(sorted(stem_beacons.items()))


def scan_hosts(reference_hostname):
    """
    scan for STEM-mode Weka hosts
    :param reference_hostname: str
    :return: a dict containing the valid STEMHost objects
    """
    stem_beacons = beacon_hosts(reference_hostname)
    hostgroup = WekaHostGroup(reference_hostname, stem_beacons)
    if not hostgroup.is_homogeneous():
        log.info("Host group is not Homogeneous!  Please verify configuration(s)")
    else:
        log.info("Host group is Homogeneous.")
    return hostgroup
