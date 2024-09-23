################################################################################################
# Weka Specific Code
################################################################################################
import curses
import ipaddress
import socket
import sys
from logging import getLogger
from sortedcontainers import SortedDict

from wekalib import signal_handling
from wekalib.exceptions import LoginError, CommunicationError, NewConnectionError
from wekalib.wekaapi import WekaApi
from wekapyutils.sthreads import default_threader
from wekapyutils.wekassh import RemoteServer, parallel, threaded_method

log = getLogger(__name__)
summary_log = getLogger("summary")



def shutdown_curses(opaque):
    try:
        curses.echo()
        curses.nocbreak()
        curses.endwin()
    except:
        pass
    log.critical("Terminated by user")


signal_handler = signal_handling(graceful_terminate=shutdown_curses)


def get_local_ips():
    """
    # get a list of local ip addresses
    :return: list of ip addresses
    """
    import netifaces
    return [netifaces.ifaddresses(iface)[netifaces.AF_INET][0]['addr'] for iface in netifaces.interfaces() if netifaces.AF_INET in netifaces.ifaddresses(iface)]

def connect(ssh_session):
    try:
        ssh_session.connect()
    except:
        log.error(f"Unable to connect to {ssh_session.hostname}")
        return False

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
        self.drives = SortedDict()
        self.drive_devs = SortedDict()
        self.nics = SortedDict()
        self.cpu_model = None
        self.num_cores = None
        self.dataplane_nics = SortedDict()
        self.total_ramGB = None
        self.version = None
        self.is_reference = False
        self.is_local = False

    def __str__(self):
        return self.name

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

        # take some of the info and put it in our object for easy reference
        self.num_cores = len(self.machine_info['cores'])
        self.cpu_model = self.machine_info['cores'][0]['model']
        self.version = self.machine_info['version']
        self.total_ramGB = int(self.machine_info["memory"]["total"] / 1024 / 1024 / 1024)

        for drive in self.machine_info['disks']:
            if drive['type'] == "DISK" and not drive['isRotational'] and not drive['isMounted'] and \
                    len(drive['pciAddr']) > 0 and drive['type'] == 'DISK':
                self.drives[drive['devName']] = drive

        # need to determine if any of the above drives are actually in use - boot devices, root drives, etc.
        # how?
        #                 "parentName": "sda",
        #                 "type": "PARTITION",
        #                 "isMounted": true,

        # remove any drives with mounted partitions from the list
        for drive in self.machine_info['disks']:
            if drive['type'] == "PARTITION" and drive['parentName'] in self.drives and drive['isMounted']:
                del self.drives[drive['parentName']]

    # STEMhost validate_nics
    def validate_nics(self):
        for net_adapter in self.machine_info['net']['interfaces']:
            if net_adapter['name'] == 'lo':  # we can't use loopback interfaces anyway
                continue

            # skip bond slaves - we'll get these from the bond (below)
            if net_adapter['bondType'] == 'SLAVE':
                log.debug(f'{self.name}: Skipping interface {self.name}/{net_adapter["name"]} - is a slave to a bond')
                continue

            # Check MTU
            if net_adapter['linkLayer'] == 'IB':
                if net_adapter['mtu'] != 2044 and net_adapter['mtu'] != 4092:
                    log.debug(f'{self.name}: Skipping {self.name}/{net_adapter["name"]} due to unsupported MTU:{net_adapter["mtu"]}')
                    continue
            elif net_adapter['linkLayer'] == 'ETH':
                if net_adapter['mtu'] < 1500 or net_adapter['mtu'] >= 10000:
                    log.debug(
                        f'{self.name}: Skipping {self.name}/{net_adapter["name"]} due to MTU {net_adapter["mtu"]} out of range')
                    continue

            # make sure it has an ipv4 address
            if len(net_adapter['ip4']) <= 0:
                log.debug(f'{self.name}: Skipping interface {self.name}/{net_adapter["name"]} - unconfigured')
                continue

            if net_adapter['bondType'] == 'NONE':  # "NONE", "BOND" and "SLAVE" are valid
                details = self.find_interface_details(net_adapter['name'])
                if details is None:
                    continue    # skip it... there's some problem with it (debugs in find_interface_details)
                self.nics[net_adapter['name']] = WekaInterface(net_adapter['linkLayer'],
                                                                   net_adapter['name'],
                                                                   f"{net_adapter['ip4']}/{net_adapter['ip4Netmask']}",
                                                                   details['speedMbps'])
                log.info(f"{self.name}: interface {self.name}/{net_adapter['name']} added to config")

            elif net_adapter['bondType'][:4] == 'BOND':  # can be "BOND_MLTI_NIC" or whatever.  Same diff to us
                # bonds don't appear in the net_adapters... have to build it from the slaves
                if len(net_adapter['name_slaves']) == 0:  # what are other values?
                    log.error(f"{self.name}/{net_adapter['name']}: bond has no slaves?; skipping")
                    continue
                log.info(f"{self.name}/{net_adapter['name']}:name_slaves = {net_adapter['name_slaves']}")
                # find an "up" slave, if any
                for slave in net_adapter['name_slaves']:
                    slave_details = self.find_interface_details(slave)
                    if slave_details is None:
                        log.error(f"issue with slave interface {slave} on host '{self.name}' - skipping")
                        continue
                    log.info(f"{self.name}: {net_adapter['name']}: slave {slave_details['ethName']} good.")
                    self.nics[net_adapter['name']] = \
                            WekaInterface(net_adapter['linkLayer'], net_adapter['name'],
                                          f"{net_adapter['ip4']}/{net_adapter['ip4Netmask']}", slave_details['speedMbps'])
                    log.info(f"{self.name}: bond {net_adapter['name']} added to config")
                        # we don't care about other slaves once we find a working one - they should all be the same
                    break   # break?
                log.error(f"{self.name}: bond {net_adapter['name']} has no up slaves - skipping")
            else:
                log.info(f"{self.name}:{net_adapter['name']} - unknown bond type {net_adapter['bondType']}")

    def find_interface_details(self, iface):
        for eth in self.machine_info['eths']:
            if eth['interface_alias'] == iface or eth['ethName'] == iface:  # changed interface_alias in newer releases
                if not (eth['validationCode'] == "OK" and eth['linkDetected']):
                    log.debug(f"Skipping interface {self.name}/{iface} - down or not validated")
                    return None   # not good/usable
                return eth
        log.debug(f"Skipping interface {self.name}/{iface} - not in eths")
        return None  # not found

    def open_api(self, ip_list=None):
        """
        Try to open a connection to the API on the host; try all listed IPs, take first one that works
        depending on how we're running, we may or may not be able to talk to the host over every ip...

        :param ip_list: a list of ip addrs
        :return: weka api object
        """
        if ip_list is None:
            ip_list = [self.name]

        #log.debug(f"host {self.name}: {ip_list}")
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
                #log.error(f"Unable to contact host {self.name}")
                continue
            except UnboundLocalError:
                log.error(f"Unable to contact host {self.name}")
                return None
            except Exception as exc:
                log.error(f"Other exception on host {self.name}: {exc}")
                continue

        if self.host_api is None:
            log.debug(f"{self.name}: unable to open api to {self.name} - skipping")
            return None
        else:
            log.debug(f"host api opened on {self.name} via {ip}")

    def lscpu(self):
        # it would be nice to be able to get json output, but some old OS versions don't support it
        self.lscpu_data = SortedDict()
        cmd_output = self.run("lscpu")
        if cmd_output.status == 0:
            # we were able to run lscpu
            outputlines = cmd_output.stdout.split('\n')
            if len(outputlines) > 0:
                #log.debug(f"got lscpu output for {self.name}")
                for line in outputlines:
                    splitlines = line.split(':')
                    if len(splitlines) > 1:
                        self.lscpu_data[splitlines[0].strip()] = splitlines[1].strip()
            else:
                log.error(f"Host {self.name}: Unable to parse lscpu output - no lines")
        else:
            log.error(f"lscpu failed on {self.name}")

    def check_source_routing(self):
        # check if the host has source-based routing set up
        self.ip_rules = SortedDict()
        cmd_output = self.run("ip rule show | grep -v all")
        if cmd_output.status == 0:
            outputlines = cmd_output.stdout.split('\n')
            if len(outputlines) > 0:
                for line in outputlines:
                    splitlines = line.split(':')
                    if len(splitlines) > 1:
                        self.ip_rules[splitlines[0].strip()] = splitlines[1].strip().split()
            else:
                log.error(f"Host {self.name}: Unable to parse 'ip rule show' output - no lines")
        else:
            log.error(f"'ip rule show' failed on {self.name}")

        if len(self.ip_rules) == 0:
            log.info(f"{self.name}: No source-based routing rules found")
            return False
        return True
        #for nic in self.nics:
        #    for rule in self.ip_rules:
        #        if rule
        #    if nic.ip in self.ip_rules:
        #        log.info(f"{self.name}: {nic} has source-based routing set up")

    def run(self, command, *args, **kwargs):

        if self.is_local:
            log.debug(f"Running command locally on {self.name}: {command}")
            import subprocess
            ssh_out = subprocess.run(command, shell=True, capture_output=True, text=True)
            ssh_out.status = ssh_out.returncode
            return ssh_out
        else:
            log.debug(f"Running command remotely on {self.name}: {command}")
            # if we need to run something there, and it doesn't have an ssh session yet, open one
            #if self.ssh_client is None:
            #    self.ssh_client = RemoteServer(self.name)
            #    self.ssh_client.connect()
            return self.ssh_client.run(command, *args, **kwargs)


class NamedDict(SortedDict):
    def __init__(self, *args, **kwargs):
        try:
            self._name = kwargs.pop('name')
        except KeyError:
            raise KeyError('a "name" keyword argument must be supplied')
        super(NamedDict, self).__init__(*args, **kwargs)

    @property
    def name(self):
        return self._name


class WekaHostGroup():
    def __init__(self, reference_host, beacons):
        """
        This routine is run before the TUI starts to scope out the cluster.

        Using reference_hostname as a basis, find the other hosts that we can make into a cluster
        The idea is to narrow down the beacons list to something that will work
        Then analyze the hosts (networks and whatnot) to see how we can configure things

        :param beacons: dict of hostname:[list of ip addrs]
        :return: a list of STEMHost objects
        """
        self.mixed_networking = False
        self.link_types = list()
        self.local_subnets = list()
        self.isrouted = False
        self.one_network = False
        self.usable_hosts = SortedDict()
        self.accessible_hosts = SortedDict()  # a dict of {ifname:(hostname)}  (set of hostnames on the nic)
        self.pingable_ips = SortedDict()
        self.networks = SortedDict()
        self.candidates = SortedDict()
        self.rejected_hosts = SortedDict()
        self.reference_host = reference_host
        #self.clients = SortedDict()

        default_threader.num_simultaneous = 5  # ssh has a default limit of 10 sessions at a time
        self.beacons = beacons
        self.weka_version = reference_host.version

        # if we're not running locally on the reference host, open an ssh session to it
        if not self.reference_host.is_local:
            self.reference_host.ssh_client = RemoteServer(self.reference_host.name)
            self.reference_host.ssh_client.connect()

        log.info(f"Getting configuration info from hosts...")
        self.create_candidates()
        log.debug(f"candidates = {list(self.candidates.keys())}")

        self.scan_machine_info()
        log.debug(f"candidates = {list(self.candidates.keys())}")
        self.check_weka_release()
        log.debug(f"candidates = {list(self.candidates.keys())}")
        self.validate_nics()    # WekaHostGroup.validate_nics
        log.debug(f"candidates = {list(self.candidates.keys())}")
        self.explore_network()
        log.debug(f"candidates = {list(self.candidates.keys())}")
        self.analyze_networks()
        log.debug(f"candidates = {list(self.candidates.keys())}")
        self.get_hardware_info()
        log.debug(f"candidates = {list(self.candidates.keys())}")


        summary_log.info("************************ Summary ************************")
        summary_log.info(f"usable_hosts = {list(self.usable_hosts.keys())}")
        summary_log.info("rejected_hosts:")
        for host, reasons in self.rejected_hosts.items():
            summary_log.info(f"    {host}: {reasons}")

    def reject_host(self, host, reason):
        try:
            log.debug(f"Rejecting {str(host)} - {reason}")
            self.candidates.pop(str(host))
        except (KeyError, NameError):
            log.debug(f"{str(host)} not in candidates list - adding to rejected list")
        if str(host) in self.rejected_hosts.keys():
            log.debug(f"{str(host)} already rejected - adding reason")
            self.rejected_hosts[str(host)].append(reason)
        else:
            self.rejected_hosts[str(host)] = [reason]

    def create_candidates(self):
        #
        for host, ip_list in self.beacons.items():
            # if we're going to do this, we have to create the STEMHost object first, not below
            log.debug(f"creating candidate for {host}")
            candidate = STEMHost(host)
            # Open an API to each host, in parallel
            log.debug(f"opening api to {host}")
            threaded_method(candidate, STEMHost.open_api, ip_list)  # schedule to run (they're slow)
            self.candidates[host] = candidate
        default_threader.run()  # run the threaded methods

        for host, candidate in self.candidates.copy().items():
            if candidate.host_api is None:
                log.info(f"Unable to communicate with {host} API - skipping")
                self.reject_host(candidate, "Unable to communicate with API")

    """
    def open_candidate_api(self):
        # weed out the ones we can't talk to or reach
        for host, candidate in self.candidates.items():
            log.debug(f"opening api to {host}")
            threaded_method(candidate, STEMHost.open_api, ip_list)  # schedule to run (they're slow)
        default_threader.run()  # run the threaded methods

        for host, candidate in self.candidates.copy().items():
            if candidate.host_api is None:
                log.info(f"Unable to communicate with {host} API - skipping")
                self.reject_host(candidate, "Unable to communicate with API")
    """

    def scan_machine_info(self):
        log.debug(f"Getting machine info from hosts...")
        parallel(self.candidates.values(), STEMHost.get_machine_info)
        # if get_machine_info fails, the host will not have a self.machine_info
        for candidate in self.candidates.copy().values():
            if candidate.machine_info is None:
                log.error(f"Error communicating with {candidate.name} - removing from list")
                self.reject_host(candidate, "Unable to fetch machine info")
                continue
        log.debug(f"Got machine info from {list(self.candidates.keys())}")

    # WekaHostGroup.validate_nics
    def validate_nics(self):
        # at this point, the reference_host might not be the same STEMhost object as the one in the candidates list
        self.reference_host.validate_nics()
        parallel(self.candidates.values(), STEMHost.validate_nics)

        # check if we're running locally on the reference host; make a note of it for .run()
        self.local_ips = get_local_ips()
        reference_host_ips = [str(iface.ip) for iface in self.reference_host.nics.values()]

        # if any of the local ips are in the reference host, then we're running locally
        self.reference_host.is_local = len(list(set(self.local_ips).intersection(reference_host_ips))) > 0
        print()

        #if len(list(set(self.local_ips).intersection(reference_host_ips))) > 0:
        #    self.reference_host.is_local = True

        """
        # do it the hard way...
        for ip in self.local_ips:
            if ip in reference_host_ips:
                self.reference_host.is_local = True
                break
        """

        """
        # find reference_host in the candidates list
        self.local_ips = get_local_ips()
        for ip in self.local_ips:
            for candidate in self.candidates.values():
                candidate_ips = [str(iface.ip) for iface in candidate.nics.values()]
                if ip in candidate_ips:
                    self.reference_host = candidate
                    candidate.is_reference = True
                    break
            if self.reference_host is not None:
                break
        if self.reference_host is None:
            log.error(f"Unable to find local host in candidates list")
            sys.exit(1)
        """

    def check_weka_release(self):
        # find hosts that can cluster with reference_hostname - they pointed us at reference_hostname for a reason
        log.info(f"Localhost is running WEKA version {self.weka_version}")
        log.info(f"Searching for other {self.weka_version} hosts...")
        for host, candidate in self.candidates.copy().items():  # copy it so we can del() from orig list
            if candidate.version != self.weka_version:
                log.info(f"    host {host} is not running v{self.weka_version} - removing from list")
                self.reject_host(candidate,
                             f"Host is running {candidate.version} - not compatible with {self.weka_version}")
                continue
            else:
                log.debug(f"    host {host} is running {self.weka_version}")
            #log.info(f"Host {host} added to list of possible cluster hosts")

    def check_weka_release_old(self):
        # find hosts that can cluster with reference_hostname - they pointed us at reference_hostname for a reason
        log.info(f"Reference Host {self.reference_host.name} is running WEKA release {self.reference_host.version}")
        log.info(f"Searching for other {self.reference_host.version} hosts...")
        for host, candidate in self.candidates.copy().items():  # copy it so we can del() from orig list
            if candidate.machine_info is None:
                log.error(f"Error communicating with {host} - removing from list")
                self.reject_host(candidate, "Error communicating with host - lacks machine info")
                continue
            elif candidate.version != self.reference_host.version:
                log.info(f"    host {host} is not running v{self.reference_host.version} - removing from list")
                self.reject_host(candidate,
                        f"Host is running {candidate.version} - not compatible with {self.reference_host.version}")
                continue
            else:
                #candidate.validate_nics()
                if len(candidate.nics) == 0:
                    log.error(f"{host} has no usable nics?  Skipping...")
                    self.reject_host(candidate, "No usable nics")
                    continue
            log.info(f"Host {host} added to list of possible cluster hosts")

    def explore_network(self):
        log.info("Preparing to explore network...")

        # find the localhost (reference_host) in the candidates list (a STEMHost object)
        #self.local_ips = get_local_ips()
        #self.reference_host = None
        """
        for ip in self.local_ips:
            for candidate in self.candidates.values():
                candidate_ips = [str(iface.ip) for iface in candidate.nics.values()]
                if ip in candidate_ips:
                    self.reference_host = candidate
                    candidate.is_reference = True
                    break
            if self.reference_host is not None:
                break
        if self.reference_host is None:
            log.error(f"Unable to find local host in candidates list")
            sys.exit(1)
        """

        # There may be a reference_host of localhost, and another copy of it with a "real" hostname
        # so we need to make sure we only have one copy of the reference_host
        for host in self.candidates.values():
            # see if this one has the same ips as the reference host
            reference_host_ips = [str(iface.ip) for iface in self.reference_host.nics.values()]
            host_ips = [str(iface.ip) for iface in host.nics.values()]
            # if len(list(set(host_ips).intersection(reference_host_ips))) > 0:   # if any of the ips match

            if reference_host_ips == host_ips:
                log.info(f"Found reference host {self.reference_host.name}")
                host.is_local = self.reference_host.is_local
                host.is_reference = True
                host.ssh_client = self.reference_host.ssh_client
                self.reference_host = host
                break

        # make sure reference_hostname can talk to the others over the dataplane networks; narrow the list,
        # and collect details of what weka hosts we can see on each nic
        # self.accessible_hosts = dict()  # a dict of {ifname:(hostname)}  (set of hostnames on the nic)
        # self.pingable_ips = dict()
        # self.numnets = dict()
        for source_interface in self.reference_host.nics.keys():
            self.accessible_hosts[source_interface] = set()  # hosts by interface on the reference host
            self.accessible_hosts[source_interface].add(self.reference_host.name)  # always add this
            self.pingable_ips[source_interface] = list()  # ips pingable from this interface
            self.networks[source_interface] = set()

        log.info("Exploring network... this may take a while")

        # set up for parallel execution ########################
        # this uses the reference host to ping all the candidates on the dataplane networks
        log.debug(f"refhost.nics = {list(self.reference_host.nics.keys())}")
        for hostname, hostobj in self.candidates.items():
            log.info(f'Looking at host {hostname}...')
            # see if the reference host can talk to the target ip on each interface
            for source_interface in self.reference_host.nics.keys():  # refhost nic
                for targetif, targetip in hostobj.nics.items():  # candidate nic
                    if hostname == self.reference_host.name and source_interface == targetif:
                        self.pingable_ips[source_interface].append(targetip)  # make sure refhost is there
                        continue  # not sure why, but ping fails on loopback anyway

                    log.debug(f"checking {hostobj.name}/{source_interface}/{targetip.ip} from {source_interface}")
                    # source_interface is the interface on the reference host
                    # hostobj is the host we're pinging
                    # targetip is the ip on the host that we're pinging
                    threaded_method(self, WekaHostGroup.ping_clients, source_interface, hostobj, targetip)
                    #self.ping_clients(source_interface, hostobj, targetip)

        # execute the pings...  ###################
        default_threader.run()   # sets self.accessible_hosts and self.pingable_ips

    def analyze_networks(self):
        # note: self.accessible_hosts is a dict of {ifname:(hostname)}  (set of hostnames on the nic)
        # note that self.pingable_ips is a dict of {ifname:[ipaddr]}  (list of ip addrs pingable from this interface)


        # open ssh to all the hosts - make sure we can get to them
        log.info(f"Opening ssh to hosts")
        self.open_ssh_toall()

        # merge the accessible_hosts sets - we need the superset for later
        log.info(f"starting network analysis")
        usable_set = set()  # a set will always be unique... no duplicates
        something_wrong = False
        for host_set in self.accessible_hosts.values():
            if len(usable_set) != 0 and host_set != usable_set:
                something_wrong = True
            usable_set = usable_set.union(host_set)

        if something_wrong:
            log.error("There are hosts that are not accessible from all interfaces - check network config")
            for iface, host_set in self.accessible_hosts.items():
                log.error(f"    hosts accessible from {iface}: {host_set}")

        # log.info(f"There are {len(usable_set)} ping-able hosts")
        for host in usable_set:
            if host in self.candidates:    # might not be if we can't ssh to it
                self.usable_hosts[host] = self.candidates[host]
        # for some odd reason, the above ping doesn't work when loopback.  Go figure
        self.usable_hosts[self.reference_host.name] = self.reference_host  # he gets left out

        if len(self.usable_hosts) != len(self.candidates):
            log.error(f"Only {len(self.usable_hosts)} of {len(self.candidates)} candidates are ping-able via dataplane")
            for host, candidate in self.candidates.items():
                if host not in self.usable_hosts:
                    log.error(f"    {host} is not ping-able via dataplane")
        else:
            log.info(f"All {len(self.usable_hosts)} hosts are ping-able via dataplane")

        log.info(f"There appear to be {len(self.usable_hosts)} usable hosts - {list(self.usable_hosts.keys())}")

        # are the other hosts on different subnets?
        for source_interface in self.reference_host.nics.keys():
            if len(self.networks[source_interface]) > 1:
                self.isrouted = True  # not completely sure this is correct... it should have routes to all the networks

        # is there more than one subnet on this host? (ie: are all the interfaces on the same subnet?)
        if not self.isrouted:    # does it really matter if we're routed?
            for source_interface, if_obj in self.reference_host.nics.items():
                if if_obj.network not in self.local_subnets:
                    self.local_subnets.append(if_obj.network) # a list of unique networks
            if len(self.local_subnets) > 1:
                self.isrouted = True  # hmm... doesn't really mean it's routed; could be just 2 subnets?
            else:
                # also - if one network and more than 1 nic, we need source-based routing?
                # not sure if this is the best place to check
                self.one_network = True

        # network link layer types
        for source_interface, if_obj in self.reference_host.nics.items():
            if if_obj.type not in self.link_types:
                self.link_types.append(if_obj.type)

        # do we have both IB and ETH interfaces? (maybe we should check this AFTER they select the dataplane?)
        if len(self.link_types) > 1:
            self.mixed_networking = True

        # go probe the hosts to see if they have a default route set, if so, we'll config weka to use it
        log.info("Probing for gateways")
        for host, host_obj in self.usable_hosts.items():
            for nicname, nic_obj in host_obj.nics.items():
                if nic_obj.type != "IB":  # we don't support gateways on IB
                    threaded_method(self, WekaHostGroup.get_gateways, host_obj, nic_obj)
                    #self.get_gateways(host_obj, nic_obj)

        default_threader.run()   # update host object with gateway info

        # check if they need source-based routing and see if they have it set up
        if self.one_network:
            log.info("There is only one network on the reference host")
            if len(self.reference_host.nics) > 1:
                log.info("There are multiple UP interfaces on the reference host")
                log.info("Checking for source-based routing")
                for hostname, host_obj in self.usable_hosts.items():
                    if not host_obj.check_source_routing():
                        log.error(f"{host_obj.name} needs source-based routing set up")
                    else:
                        log.info(f"{host_obj.name} appears to have source-based routing set up")

    def ping_clients(self, source_interface, hostobj, targetip):
        """
        # ping the target host interface from the reference host (may be more than one interface per)
        :param source_interface: The interface on this host we want to ping from
        :type source_interface:
        :param hostobj:  target STEMhost object
        :type STEMHost:
        :param targetip: target ip address on the target host
        :type WekaInterface:
        :return: Fills in self.accessible_hosts and self.pingable_ips
        :rtype: None
        """
        hostname = hostobj.name

        # vince- need to determine if we're running locally or remotely!
        # use object .run() method to run the command!
        # be sure to use the reference host!

        #import subprocess
        log.debug(f"running:  ping -c1 -W1 -I {source_interface} {targetip.ip}")
        ssh_out = self.reference_host.run(f"ping -c1 -W1 -I {source_interface} {targetip.ip}") # , shell=True, capture_output=True, text=True)
        if ssh_out.status == 0:
            log.debug(f"Ping from {self.reference_host.name}/{source_interface} to target {hostname}/{targetip} successful - adding {hostname} to accessible_hosts")
            # make sure we can ssh to the host
            #if hostobj.ssh_client is None:
            #    hostobj.ssh_client = RemoteServer(hostname)
            #    hostobj.ssh_client.connect()
            #self.clients[hostname] = hostobj.ssh_client

            # we were able to ping the host!  add it to the set of hosts we can access via this IF
            self.accessible_hosts[source_interface].add(hostname)
            self.pingable_ips[source_interface].append(targetip)
            if targetip.network not in self.networks[source_interface]:  # do this elsewhere?
                self.networks[source_interface].add(targetip.network)  # note unique networks (should get blake's)
        else:
            log.debug(f"Ping from {self.reference_host.name}/{source_interface} target {hostname}/{targetip} failed with rc={ssh_out.status} - skipping")

    def get_gateways(self, host, nic):
        log.info(f"probing gateway for {host}/{nic.name}")

        # try google DNS because we're sure they don't have it on their network...
        if not self.probe_gateway(host, nic, '8.8.8.8'):
            # no default gateway, see if there are any gateways to the other nodes...
            for interface, target_list in self.pingable_ips.items():
                for target in target_list:
                    if self.probe_gateway(host, nic, target.ip):
                        break
        if nic.gateway is not None:
            log.info(f"    {host}/{nic.name} has gateway {nic.gateway}")
        else:
            log.warning(f"    {host}/{nic.name} has no dataplane gateway(s)")
        return  # gateway is set in nic, if it was found

    def probe_gateway(self, host, nic, target):
        cmd_output = host.run(f"ip route get {target} oif {nic.name}")

        if cmd_output.status == 0:
            outputlines = cmd_output.stdout.split('\n')
            if len(outputlines) > 0:
                splitlines = outputlines[0].split()
                if splitlines[1] == 'via':  # There's a gateway!
                    nic.gateway = splitlines[2]
                    return True
        else:
            log.debug(f"Error executing 'ip route get {target} oif {nic.name}' on {host}:{nic.name}:" +
                      f" return code={cmd_output.status}," +
                      f" stderr={list(cmd_output.stderr)}")
        return False

    def open_ssh_toall(self):
        clients = dict()
        for host, host_obj in self.candidates.items():
            # open sessions to all the hosts
            if host_obj.ssh_client is None:
                host_obj.ssh_client = RemoteServer(host)
            clients[host] = host_obj.ssh_client
        parallel(clients.values(), RemoteServer.connect)
        #parallel(clients.values(), connect)
        for host, host_obj in self.candidates.copy().items():
            if not host_obj.ssh_client.connected:
                log.error(f"Unable to open ssh session to {host} - removing from list")
                self.reject_host(host_obj, "Unable to open ssh session")
        pass
        #parallel(clients.values(), self.do_connect, self)

    def is_homogeneous(self):
        """
        # check if all the hosts are the same.  Note ones that are different.
        :return:
        """

        cores = SortedDict()  # dict of {numcores: [hosts]}
        hyperthreads = SortedDict()
        ram = SortedDict()  # dict of {ram_GB: [hosts]}
        drives = SortedDict()  # dict of {num_drives: [hosts]}
        drive_sizes = SortedDict()
        nics = SortedDict()
        nic_names = SortedDict()
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

            # check that they all have the same number of usable nics... ? not sure if this is right
            num_nicslist = nics.get(len(host_obj.nics), list())
            num_nicslist.append(str(host_obj))
            nics[len(host_obj.nics)] = num_nicslist

            for iface, nic in host_obj.nics.items():
                nic_namelist = nic_names.get(iface, list())
                nic_namelist.append(host_obj.name)
                nic_names[iface] = nic_namelist

        if len(cores) != 1:
            homo = False
            log.error("Hosts do not have a homogeneous number of cores")
            for corecount, corehostlist in cores.items():
                log.info(f"  There are {len(corehostlist)} hosts with {corecount} cores: {corehostlist}")

        if len(hyperthreads) != 1:
            log.error("Not all hosts share hyperthread/SMT setting")
            for value, hostlist in hyperthreads.items():
                log.info(f"  There are {len(hostlist)} hosts with Hyperthreading/SMT {value}: {hostlist}")

        if len(ram) != 1:
            homo = False
            log.error("Hosts do not have a homogeneous amount of ram")
            for ram_GB, ramhostlist in ram.items():
                log.info(f"  There are {len(ramhostlist)} hosts with {ram_GB} GB of RAM: {ramhostlist}")

        if len(drives) != 1:
            homo = False
            log.error("Hosts do not have a homogeneous number of drives")
            for num_drives, drivehostlist in drives.items():
                log.info(f"  There are {len(drivehostlist)} hosts with {num_drives} drives: {drivehostlist}")

        if len(nics) != 1:
            homo = False
            log.error("Hosts do not have a homogenous number of usable nics")
            for num_nics, niclist in nics.items():
                log.info(f"  There are {len(niclist)} hosts with {num_nics} working dataplane NICs: {niclist}")

        if len(drive_sizes) != 1:
            homo = False
            log.error("Hosts do not have a homogeneous drive sizes")
            for drive_size, drivehostlist in drive_sizes.items():
                log.info(f"  There are {len(drivehostlist)} hosts with " +
                         f"{round(drive_size / 1000 / 1000 / 1000 / 1000, 2)} TB/" +
                         f"{round(drive_size / 1024 / 1024 / 1024 / 1024, 2)} TiB " +
                         f"drives: {drivehostlist}")

        if len(self.networks) != len(nic_names):
            homo = False
            log.info(f"Hosts have varying network interface names")
            for name, name_list in nic_names.items():
                log.info(f"  interface {name}: {name_list}")

        return homo

    def get_hardware_info(self):
        """
        # get info on the hosts
        :return:
        """
        # Don't call ssh-using methods in parallel - can run the system out of ssh sessions
        for host, host_obj in self.usable_hosts.items():
            host_obj.lscpu()

        for host, host_obj in self.usable_hosts.items():
            if 'Thread(s) per core' in host_obj.lscpu_data:
                threads = host_obj.lscpu_data.get('Thread(s) per core', '0')
                host_obj.hyperthread = False if threads == '1' else True
                host_obj.threads_per_core = int(threads)
                if host_obj.threads_per_core == 0:
                    log.error(f"Host {host}: Unable to parse lscpu output -TPC=0")
                else:
                    log.debug(f"{host} hyperthreading/SMT is {host_obj.hyperthread}")
            else:
                log.error(f"Host {host}: Unable to parse lscpu output - TPC not found")


def beacon_hosts():
    """
    :param hostname: str
    :return: a dict of hostname:[list of ip addrs]
    """
    # start with the hostname given; get a list of beacons from it
    log.info("finding hosts...")
    reference_host = STEMHost("localhost")
    reference_host.open_api([reference_host.name])
    if reference_host.host_api is None:
        log.info(f"ERROR: Unable to contact host '{reference_host.name}' via API")
        sys.exit(1)  # very hard error

    if not reference_host.host_api.STEMMode:
        log.info(f"reference host {reference_host.name} is already part of a cluster - aborting")
        sys.exit(1)

    # returns a dict of {ipaddr:hostname}
    beacons = reference_host.host_api.weka_api_command("cluster_list_beacons", parms={})

    # make a dict of {hostname:[ipaddr]}
    stem_beacons = dict()   # SortedDict()
    for ip, hostname in beacons.items():
        if hostname not in stem_beacons:
            stem_beacons[hostname] = [ip]
        else:
            stem_beacons[hostname].append(ip)

    log.info("Beacons found:")
    for host, ips in stem_beacons.items():
        log.info(f"    {host}: {sorted(ips)}")

    return stem_beacons


def scan_hosts(hostlist):
    """
    scan for STEM-mode Weka hosts
    :param reference_hostname: str
    :return: a dict containing the valid STEMHost objects
    """
    # make sure we can talk to the local weka container/host
    if len(hostlist) == 0:
        reference_host = STEMHost("localhost")
    else:
        reference_host = STEMHost(hostlist[0])  # use the first host
    reference_host.open_api([reference_host.name])
    if reference_host.host_api is None:
        log.info(f"ERROR: Unable to contact host '{reference_host.name}' via API")
        sys.exit(1)  # very hard error

    # get the weka version
    reference_host.get_machine_info()
    if reference_host.machine_info is None:
        log.info(f"ERROR: Error getting machine info from '{reference_host.name}' via API")
        sys.exit(1)  # very hard error

    weka_version = reference_host.version
    reference_host.is_reference = True

    errors = False
    # were we given a list of hosts to scan? (or a single host... then get beacons)
    if len(hostlist) <= 1:
        log.info("looking for WEKA beacons on localhost")
        stem_beacons = beacon_hosts()
        # if we weren't given a list of hosts, we must be running on one of the nodes
        reference_host.is_local = True
    else:
        # reference_host.is_local = False   # not needed - implied/default
        log.info("Using given hostnames/ips instead of beacons...")
        stem_beacons = dict()   # SortedDict()
        ip4 = None
        # validate the hostnames/ips
        for host in hostlist:
            try:
                ip4 = ipaddress.ip_address(host)
            except ValueError as exc:
                try:
                    ip4 = socket.gethostbyname(host)
                except socket.gaierror as exc:
                    errors = True
                    log.error(f"Unable to resolve hostname {host}: {exc}")
                    log.error(f"hosts must be resolvable to ip addresses, or valid ip addresses")

            # put them in the same format as beacons, so we can use the same code to parse them

            if ip4 is None:
                errors = True
                log.error(f"Unable to resolve hostname or invalid ip addr: {host}")
            if ip4 == host:
                # we were given ip addresses, not hostnames
                stem_beacons[host] = [host]
            else:
                # we were given hostnames, and ip4 is the ip address, if it resolves
                stem_beacons[host] = [str(ip4)]
        if errors:
            log.critical("there were errors resolving hostnames - please specify valid hosts and retry.  Aborting")
            sys.exit(1)

    log.info(f"list of potential WEKA hosts: {list(stem_beacons.keys())}")
    hostgroup = WekaHostGroup(reference_host, stem_beacons)
    log.info("************************** Analysis **************************")
    if not hostgroup.is_homogeneous():
        log.info("Host group is not Homogeneous!  Please verify configuration(s)")
    else:
        log.info("Host group is Homogeneous.")
    return hostgroup
