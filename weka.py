################################################################################################
# Weka Specific Code
################################################################################################
import ipaddress
import sys
from collections import OrderedDict
from logging import getLogger

from wekalib.exceptions import LoginError, CommunicationError, NewConnectionError
from wekalib.wekaapi import WekaApi
from wekapyutils.sthreads import default_threader
from wekapyutils.wekassh import RemoteServer, parallel, threaded_method

log = getLogger(__name__)


class WekaInterface(ipaddress.IPv4Interface):
    def __init__(self, linklayer, name, address, speed):
        self.type = linklayer
        self.name = name
        self.speed = speed
        self.gateway = None
        super(WekaInterface, self).__init__(address)


class STEMHost(object):
    def __init__(self, name):
        self.name = name
        self.host_api = None
        self.machine_info = None

    def get_machine_info(self):
        """
        get the info_hw output from the API
        """
        try:
            self.machine_info = self.host_api.weka_api_command("machine_query_info", parms={})
        except LoginError:
            print(f"host {self.name} failed login querying info")
            errors = True
        except CommunicationError:
            print(f"Error communicating with host {self.name} querying info")
            errors = True

        self.num_cores = len(self.machine_info['cores'])
        self.cpu_model = self.machine_info['cores'][0]['model']
        self.drives = dict()
        self.drive_devs = dict()
        self.nics = dict()
        self.version = self.machine_info['version']
        # self.info_hw = info_hw  # save a copy in case we need it
        self.dataplane_nics = dict()
        self.total_ramGB = self.machine_info["memory"]["total"] / 1024 / 1024 / 1024

        for drive in self.machine_info['disks']:
            if drive['type'] == "DISK" and not drive['isRotational'] and not drive['isMounted'] and \
                    len(drive['pciAddr']) > 0 and drive['type'] == 'DISK':
                # not drive['isSwap'] and \     # pukes now; no longer there in 3.13
                #self.drives[drive['devName']] = drive['devPath']
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
            if (4000 < net_adapter['mtu'] < 10000) and len(net_adapter['ip4']) > 0:
                # if details['ethBondingMaster'] != '':  # what are the other values?
                #    print(f"{name}:{net_adapter['name']}:ethBondingMaster = {details['ethBondingMaster']}")
                #    pass
                if net_adapter['bondType'] == 'NONE':  # "NONE", "BOND" and "SLAVE" are valid
                    details = self.find_interface_details(net_adapter['name'])
                elif net_adapter['bondType'] == 'BOND':
                    details = self.find_bond_details(net_adapter['name'])
                else:
                    continue  # skip slaves

                if len(net_adapter['name_slaves']) != 0:  # what are other values?
                    print(f"{self.name}:{net_adapter['name']}:name_slaves = {net_adapter['name_slaves']}")
                    pass

                # make sure we were able to get the details we need
                if details is None:
                    log.error(f"no details available for {net_adapter['name']} on host '{self.name}' - skipping")
                    continue

                # check this way so it doesn't puke
                val_code = details.get('validationCode', None)
                link = details.get('linkDetected', None)
                speed = details.get('speedMbps', None)

                if val_code is None:
                    log.error(f"val_code is None for {net_adapter['name']} on host '{self.name}' - skipping")
                    continue
                if link is None:
                    log.error(f"link is None for {net_adapter['name']} on host '{self.name}' - skipping")
                    continue
                if speed is None:
                    log.error(f"speed is None for {net_adapter['name']} on host '{self.name}' - skipping")
                    continue

                if details['validationCode'] == "OK" and details['linkDetected']:
                    self.nics[net_adapter['name']] = \
                        WekaInterface(net_adapter['linkLayer'],
                                      # details['interface_alias'],
                                      net_adapter['name'],
                                      f"{net_adapter['ip4']}/{net_adapter['ip4Netmask']}",
                                      details['speedMbps'])

    def find_interface_details(self, iface):
        for eth in self.machine_info['eths']:
            if eth['interface_alias'] == iface:
                return eth
        return None

    def find_bond_details(self, iface):
        for eth in self.machine_info['eths']:
            if eth['ethBondingMaster'] == iface:
                return eth
        return None

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


dataplane_hostsfile = dict()


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
        print(f"Getting configuration info from hosts...")
        for host, ip_list in self.beacons.items():
            # if we're going to do this, we have to create the STEMHost object first, not below
            candidate = STEMHost(host)
            # print(f"Opening API to {host}")
            log.info(f"opening api to {host}")
            threaded_method(candidate, STEMHost.open_api, ip_list)  # schedule to run (they're slow)
            candidates[host] = candidate
            # candidate.open_api(ip_list)

        default_threader.run()  # run the threaded methods

        for host, candidate in candidates.copy().items():
            if candidate.host_api is None:
                print(f"Unable to communicate with {host} - skipping")
                errors = True
                del candidates[host]  # remove it from the list
                # continue  # nope, so move on to next host

            # candidate.get_machine_info()
            # if candidate.machine_info is None:
            #    errors = True
            #    continue  # skip it if unable to get the info

        parallel(candidates.values(), STEMHost.get_machine_info)

        for host, candidate in candidates.copy().items():
            if candidate.machine_info is None:
                print(f"Error communicating with {host}")
                del candidates[host]  # remove it from the list
            print(f"    Host {host} is a STEM-mode instance running release {candidate.machine_info['version']}")
            # candidates[host] = candidate

        # if errors:
        #    print("Errors communicating (api) with some hosts.")

        # find the basis host (the one they gave us on the command line)
        if self.reference_hostname not in candidates:
            # something is amiss - the host they told us to talk to doesn't list itself as a STEM host?
            print(f"{self.reference_hostname} isn't in the list of good hosts?")
            sys.exit(1)

        self.referencehost_obj = candidates[self.reference_hostname]

        # find hosts that can cluster with reference_hostname - they pointed us at reference_hostname for a reason
        for hostname, hostobj in candidates.copy().items():  # copy() - py3 doesn't like a dict changing
            if hostobj.version != self.referencehost_obj.version:
                print(f"host {hostname} is not running v{self.referencehost_obj.version} - ignoring")
                del candidates[hostname]
            # else:
            #    candidates2[hostname] = hostobj

        # del candidates

        print("Preparing to explore network...")
        # self.ssh_client = self.open_ssh_connection(self.reference_hostname)  # open an ssh to the reference host
        self.ssh_client = RemoteServer(self.reference_hostname)
        self.ssh_client.connect()

        # not sure this is still needed
        if self.ssh_client is None:
            log.error(f"ERROR: unable to ssh to {self.reference_hostname}")
            sys.exit(1)
            # self.usable_hosts = candidates2
            # return

        # make sure reference_hostname can talk to the others over the dataplane networks; narrow the list,
        # and collect details of what weka hosts we can see on each nic
        self.accessible_hosts = dict()  # a dict of {ifname:(hostname)}  (set of hostnames on the nic)
        self.pingable_ips = dict()
        self.numnets = dict()
        for source_interface in self.referencehost_obj.nics.keys():
            self.accessible_hosts[source_interface] = set()  # hosts by interface on the reference host
            self.accessible_hosts[source_interface].add(self.reference_hostname)  # always add this
            self.pingable_ips[source_interface] = list()
            self.numnets[source_interface] = set()

        print("Exploring network... this may take a while")
        for hostname, hostobj in candidates.items():
            print(f'Looking at host {hostname}...')
            # see if the reference host can talk to the target ip on each interface
            for source_interface in self.referencehost_obj.nics.keys():
                for targetif, targetip in hostobj.nics.items():
                    if hostname == reference_hostname and source_interface == targetif:
                        self.pingable_ips[source_interface].append(
                            targetip)  # should only add the ip on the source interface?
                        continue  # not sure why, but ping fails on loopback anyway

                    threaded_method(self, WekaHostGroup.ping_clients, source_interface, hostobj, targetip)

        default_threader.run()

        # merge the accessible_hosts sets - we need the superset for later
        usable_set = set()  # should we really be using sets here?  A dict might work easier
        self.usable_hosts = dict()  # definitive list (well, dict) of hosts
        for host_set in self.accessible_hosts.values():
            if len(usable_set) != 0 and host_set != usable_set:
                log.warning("Not all hosts are accessible from all interfaces - check network config")
            usable_set = usable_set.union(host_set)
        for host in usable_set:
            self.usable_hosts[host] = candidates[host]
        # for some odd reason, the above ping doesn't work when loopback.  Go figure
        self.usable_hosts[self.referencehost_obj.name] = self.referencehost_obj  # he gets left out

        # are the other hosts on different subnets?
        self.isrouted = False
        for source_interface in self.referencehost_obj.nics.keys():
            if len(self.numnets[source_interface]) > 1:
                self.isrouted = True

        # is there more than one subnet on this host? (ie: are all the interfaces on the same subnet?)
        if not self.isrouted:
            self.local_subnets = []
            for source_interface, if_obj in self.referencehost_obj.nics.items():
                if if_obj.network not in self.local_subnets:
                    self.local_subnets.append(if_obj.network)
            if len(self.local_subnets) > 1:
                self.isrouted = True

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
        print(f"Opening ssh to hosts")
        self.open_ssh_toall()

        default_threader.num_simultaneous = 5  # ssh has a default limit of 10 sessions at a time
        self.host_out = dict()
        print("Probing for gateways")
        for host, host_obj in self.usable_hosts.items():
            for nicname, nic_obj in host_obj.nics.items():
                # threaded_method(host_obj, WekaHostGroup.get_gateways, host_obj, nic_obj)
                self.get_gateways(host_obj, nic_obj)
        # parallel(self, WekaHostGroup.get_gateways)
        # default_threader.run()

    def ping_clients(self, source_interface, hostobj, targetip):
        hostname = hostobj.name
        ssh_out = self.ssh_client.run(f"ping -c1 -W1 -I {source_interface} {targetip.ip}")
        if ssh_out.status == 0:
            # we were able to ping the host!  add it to the set of hosts we can access via this IF
            self.accessible_hosts[source_interface].add(hostname)
            self.pingable_ips[source_interface].append(targetip)
            dataplane_hostsfile[hostname] = targetip.ip
            if targetip.network not in self.numnets[source_interface]:
                self.numnets[source_interface].add(targetip.network)  # note unique networks
        else:
            log.debug(f"From {source_interface} target {hostname}-{targetip} failed.")

    def get_gateways(self, host, nic):
        log.info(f"probing gateway for {host}/{nic.name}")
        # determine which nic.name on the reference host we're going to look at... ie: which network
        for ref_nic in self.referencehost_obj.nics.values():
            if nic.network == ref_nic.network:
                target_interface = ref_nic.name
        for target in self.pingable_ips[target_interface]:
            cmd_output = host.ssh_client.run(f"ip route get {target} oif {nic.name}")

            outputlines = cmd_output.stdout.split('\n')
            if len(outputlines) > 0:
                log.debug(f"got output for {host}/{nic.name}")
                splitlines = outputlines[0].split()
                if splitlines[1] == 'via':  # There's a gateway!
                    nic.gateway = splitlines[2]
                    print(f"    Host {host}:{nic.name} has gateway {nic.gateway}")
                    break
            else:
                log.error(f"Error executing 'ip route get' on {host}:{nic.name}:" +
                          f" return code={cmd_output.exit_code}," +
                          f" stderr={list(cmd_output.stderr)}")

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

            # check RAM
            ramhostlist = ram.get(int(host_obj.total_ramGB), list())
            ramhostlist.append(host)
            ram[int(host_obj.total_ramGB)] = ramhostlist

            # check # of drives - {numdrives: [list of host objects]}
            drivehostlist = drives.get(len(host_obj.drives), list())
            drivehostlist.append(host_obj)
            drives[len(host_obj.drives)] = drivehostlist

            #these_drives = drive_sizes.get(host_obj.drives, list())   # returns list of drives
            # find the host_obj.machine_info.disks entry (its a list) where dev_path == these_drives
            for drive in host_obj.drives.values():
                drive_size_hostlist = drive_sizes.get(drive['sizeBytes'], list())
                if host not in drive_size_hostlist:
                    drive_size_hostlist.append(host)
                drive_sizes[drive['sizeBytes']] = drive_size_hostlist


        if len(cores) != 1:
            homo = False
            log.info("Hosts do not have a homogeneous number of cores")
            for corecount, corehostlist in sorted(cores.items()):
                log.info(f"  There are {len(corehostlist)} hosts with {corecount} cores: {corehostlist}")

        if len(ram) != 1:
            homo = False
            log.info("Hosts do not have a homogeneous amount of ram")
            for ram_GB, ramhostlist in sorted(ram.items()):
                log.info(f"  There are {len(ramhostlist)} hosts with {ram_GB} GB of RAM: {ramhostlist}")

        if len(drives) != 1:
            homo = False
            log.info("Hosts do not have a homogeneous number of drives")
            for num_drives, drivehostlist in sorted(drives.items()):
                log.info(f"  There are {len(drivehostlist)} hosts with {num_drives} GB of RAM: {drivehostlist}")

        if len(drive_sizes) != 1:
            homo = False
            log.info("Hosts do not have a homogeneous drive sizes")
            for drive_size, drivehostlist in sorted(drive_sizes.items()):
                log.info(f"  There are {len(drivehostlist)} hosts with {int(drive_size/1000/1000/1000)} GB size drives: {drivehostlist}")

        return homo

def beacon_hosts(hostname):
    """
    :param hostname: str
    :return: a dict of hostname:[list of ip addrs]
    """
    # start with the hostname given; get a list of beacons from it
    print("finding hosts...")
    reference_host = STEMHost(hostname)
    reference_host.open_api([hostname])
    if reference_host.host_api is None:
        print(f"ERROR: Unable to contact host '{hostname}'")
        sys.exit(1)  # very hard error

    if not reference_host.host_api.STEMMode:
        print(f"host {hostname} is already part of a cluster")
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
        print(f"{host}: {sorted(ips)}")

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
