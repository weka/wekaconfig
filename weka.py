################################################################################################
# Weka Specific Code
################################################################################################
import ipaddress
import socket
import sys
from logging import getLogger

log = getLogger(__name__)

try:
    from pssh.clients import SSHClient, ParallelSSHClient
except ImportError:
    from pssh.clients.ssh import SSHClient, ParallelSSHClient

import getpass

from wekalib.exceptions import LoginError, CommunicationError, NewConnectionError
from wekalib.wekaapi import WekaApi


class WekaInterface(ipaddress.IPv4Interface):
    def __init__(self, linklayer, name, address, speed):
        self.type = linklayer
        self.name = name
        self.speed = speed
        self.gateway = None
        super(WekaInterface, self).__init__(address)


class STEMHost(object):
    def __init__(self, name, info_hw):
        self.name = name
        self.num_cores = len(info_hw['cores'])
        self.cpu_model = info_hw['cores'][0]['model']
        self.drives = dict()
        self.drive_devs = dict()
        self.nics = dict()
        self.version = info_hw['version']
        self.info_hw = info_hw  # save a copy in case we need it
        self.dataplane_nics = dict()
        self.total_ramGB = self.info_hw["memory"]["total"] / 1024 / 1024 / 1024

        for drive in info_hw['disks']:
            if drive['type'] == "DISK" and not drive['isRotational'] and not drive['isMounted'] and \
                    len(drive['pciAddr']) > 0 and drive['type'] == 'DISK':
                #self.drives[drive['devPath']] = drive['pciAddr']
                self.drives[drive['devName']] = drive['devPath']

        # need to determine if any of the above drives are actually in use - boot devices, root drives, etc.
        # how?
        #                 "parentName": "sda",
        #                 "type": "PARTITION",
        #                 "isMounted": true,

        # remove any drives with mounted partitions from the list
        for drive in info_hw['disks']:
            if drive['type'] == "PARTITION" and drive['isMounted'] and drive['parentName'] in self.drives:
                del self.drives[drive['parentName']]

        for net_adapter in info_hw['net']['interfaces']:
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
                    print(f"{name}:{net_adapter['name']}:name_slaves = {net_adapter['name_slaves']}")
                    pass
                if details['validationCode'] == "OK" and details['linkDetected']:
                    self.nics[net_adapter['name']] = \
                        WekaInterface(net_adapter['linkLayer'],
                                      # details['interface_alias'],
                                      net_adapter['name'],
                                      f"{net_adapter['ip4']}/{net_adapter['ip4Netmask']}",
                                      details['speedMbps'])

    def find_interface_details(self, iface):
        for eth in self.info_hw['eths']:
            if eth['interface_alias'] == iface:
                return eth
        return None

    def find_bond_details(self, iface):
        for eth in self.info_hw['eths']:
            if eth['ethBondingMaster'] == iface:
                return eth
        return None

    def __str__(self):
        return self.name


def resolve_hostname(hostname):
    try:
        socket.gethostbyname(hostname)
    except socket.gaierror:
        return False
    except Exception:
        raise
    return True


def beacon_hosts(hostname):
    """
    :param hostname: str
    :return: a dict of hostname:[list of ip addrs]
    """
    # start with the hostname given; get a list of beacons from it
    print("finding hosts...")
    api = open_api(hostname)
    if api is None:
        print(f"ERROR: Unable to contact host '{hostname}'")
        sys.exit(1)  # very hard error

    if not api.STEMMode:
        print(f"host {hostname} is already part of a cluster")
        sys.exit(1)

    # returns a dict of {ipaddr:hostname}
    beacons = api.weka_api_command("cluster_list_beacons", parms={})

    # make a dict of {hostname:[ipaddr]}
    stem_beacons = dict()
    for ip, hostname in beacons.items():
        if hostname not in stem_beacons:
            stem_beacons[hostname] = [ip]
        else:
            stem_beacons[hostname].append(ip)

    for host, ips in stem_beacons.items():
        print(f"{host}: {ips}")

    return stem_beacons


def open_api(host, ip_list=None):
    """
    Try to open a connection to the API on the host; try all listed IPs, take first one that works
    depending on how we're running, we may or may not be able to talk to the host over every ip...

    :param ip_list: a list of ip addrs
    :return: weka api object
    """
    if ip_list is None:
        ip_list = [host]

    host_api = None
    log.debug(f"host {host}: {ip_list}")
    for ip in ip_list:
        try:
            log.debug(f"{host}: trying on {ip}")
            host_api = WekaApi(ip, scheme="http", verify_cert=False)
            break
        except LoginError:
            log.debug(f"host {host} failed login on ip {ip}?")
            continue
        except CommunicationError as exc:
            log.debug(f"Error opening API for host {host} on ip {ip}: {exc}")
            continue
        except NewConnectionError as exc:
            log.error(f"Unable to contact host {host} - is weka installed there?")
            continue
        except Exception as exc:
            log.error(f"Other exception on host {host}: {exc}")
            continue

    if host_api is None:
        log.debug(f"{host}: unable to open api to {host}")
        return None
    else:
        log.debug(f"host api opened on {host} via {ip}")
        return host_api


def get_machine_info(host, host_api):
    """
    get the info_hw output from the API
    :param host: hostname
    :param host_api: weka api object
    :return: info_hw output
    """
    machine_info = None
    try:
        machine_info = host_api.weka_api_command("machine_query_info", parms={})
    except LoginError:
        print(f"host {host} failed login querying info")
        errors = True
    except CommunicationError:
        print(f"Error communicating with host {host} querying info")
        errors = True

    return machine_info


def ask_for_credentials():
    actual_user = getpass.getuser()
    print(f"Username({actual_user}): ", end='')
    user = input()
    if len(user) == 0:
        user = actual_user

    password = getpass.getpass()
    print()
    return (user, password)


def open_ssh_connection(hostname):
    """
    reliably open an ssh connection to the host - does not return unless successful
    :param hostname:
    :return:
    """
    ssh_client = None
    try:
        # try with keys
        ssh_client = SSHClient(hostname, num_retries=1, retry_delay=1)
    except:
        pass

    while ssh_client is None:
        # keys didn't work - ask for user/password - keep trying if they mistype it
        print(f"Please enter credentials for {hostname}")
        user, password = ask_for_credentials()
        try:
            ssh_client = SSHClient(hostname,
                                   user=user,
                                   password=password,
                                   num_retries=1, retry_delay=1)
        except:
            pass

    return ssh_client


dataplane_hostsfile = dict()


def get_gateways(hostlist, ref_hostname, user, password):
    clients = dict()
    host_out = dict()
    print("Searching for gateways...")
    for host, host_obj in hostlist.items():
        # open sessions to all the hosts
        print(f"Opening ssh to {host}")
        try:
            clients[host] = SSHClient(host,
                                      user=user,
                                      password=password,
                                      proxy_host=ref_hostname,
                                      num_retries=1, retry_delay=1)
        except:
            continue  # should a failure here be catastrophic?

        host_out[host] = dict()
        for nic, nic_obj in host_obj.nics.items():
            print(f"    Scanning {host}:{nic}")
            # note - this is asynchronous...
            nic_obj.gateway = None
            host_out[host][nic_obj] = clients[host].run_command(f"ip route get 8.8.8.8 oif {nic}")

    # now collect the output
    for host, host_obj in hostlist.items():
        for nic_obj, cmd_output in host_out[host].items():
            outputlines = list(cmd_output.stdout)
            if outputlines[0][1] == 'via':  # There's a gateway!
                nic_obj.nics.gateway = outputlines[0][2]
                print(f"    Host {host}:{nic} has gateway {nic_obj.nics.gateway}")


class WekaHostGroup():
    def __init__(self, reference_hostname, beacons):

        # def find_valid_hosts(reference_hostname, beacons):
        """
        Using reference_hostname as a basis, find the other hosts that we can make into a cluster
        The idea is to narrow down the beacons list to something that will work

        :param reference_hostname: hostname of the starter host (given on command line)
        :param beacons: dict of hostname:[list of ip addrs]
        :return: a list of STEMHost objects
        """
        self.beacons = beacons
        if reference_hostname == "localhost":
            import platform
            self.reference_hostname = platform.node()
            ref_is_local = True  # note that we don't need to use ssh to run commands here
        else:
            self.reference_hostname = reference_hostname  # for now
            ref_is_local = False  # note that we DO need to use ssh to run commands on this host

        candidates = dict()
        errors = False
        # cycle through the beacon hosts, and fetch their HW info, create STEMHosts
        print(f"Getting configuration info from hosts...")
        for host, ip_list in self.beacons.items():
            host_api = open_api(host, ip_list)

            if host_api is None:
                print(f"Unable to communicate with {host} - skipping")
                errors = True
                continue  # nope, so move on to next host

            machine_info = get_machine_info(host, host_api)
            if machine_info is None:
                errors = True
                continue  # skip it if unable to get the info

            print(f"    Host {host} is a STEM-mode instance running release {machine_info['version']}")
            candidates[host] = STEMHost(host, machine_info)

        if errors:
            print("Errors communicating (api) with some hosts.")
            # time.sleep(5.0)

        # find the basis host (the one they gave us on the command line)
        if self.reference_hostname not in candidates:
            print(f"{self.reference_hostname} isn't in the list of good hosts?")
            sys.exit(1)

        self.referencehost_obj = candidates[self.reference_hostname]

        candidates2 = dict()
        # find hosts that can cluster with reference_hostname - they pointed us at reference_hostname for a reason
        for hostname, hostobj in candidates.items():
            if hostobj.version != self.referencehost_obj.version:
                print(f"host {hostname} is not running v{self.referencehost_obj.version} - ignoring")
            else:
                candidates2[hostname] = hostobj

        del candidates

        print("Exploring network...")
        self.ssh_client = open_ssh_connection(self.reference_hostname)

        if self.ssh_client is None:
            print(f"unable to ssh to {self.reference_hostname}")
            self.usable_hosts = candidates2
            return

        # make sure reference_hostname can talk to the others over the dataplane networks; narrow the list

        self.accessible_hosts = dict()  # a dict of {ifname:(hostname)}  (set of hostnames on the nic)
        self.pingable_ips = dict()
        numnets = dict()
        for source_interface in self.referencehost_obj.nics.keys():
            self.accessible_hosts[source_interface] = set()  # hosts by interface on the reference host
            self.accessible_hosts[source_interface].add(self.reference_hostname)  # always add this
            self.pingable_ips[source_interface] = list()
            numnets[source_interface] = set()
            for hostname, hostobj in candidates2.items():
                for targetif, targetip in hostobj.nics.items():
                    if hostname == reference_hostname and source_interface == targetif:
                        self.pingable_ips[source_interface].append(targetip) # should only add the ip on the source interface?
                        continue  # not sure why, but ping fails on loopback anyway
                    ssh_out = self.ssh_client.run_command(f"ping -c1 -W1 -I {source_interface} {targetip.ip}")
                    junk = list(ssh_out.stdout)  # gather output so we can get return code
                    if ssh_out.exit_code == 0:
                        # we were able to ping the host!  add it to the set of hosts we can access via this IF
                        self.accessible_hosts[source_interface].add(hostobj.name)
                        self.pingable_ips[source_interface].append(targetip)
                        dataplane_hostsfile[hostname] = targetip.ip
                        if targetip.network not in numnets[source_interface]:
                            numnets[source_interface].add(targetip.network)  # note unique networks
                    else:
                        print(f"{hostname}: from {source_interface} target: {targetip} failed.")

        # merge the accessible_hosts sets - we need the superset for later
        usable_set = set()  # should we really be using sets here?  A dict might work easier
        self.usable_hosts = dict()  # definitive list (well, dict) of hosts
        for host_set in self.accessible_hosts.values():
            if len(usable_set) != 0 and host_set != usable_set:
                print("WARNING: Not all hosts are accessible from all interfaces - check network config")
            usable_set = usable_set.union(host_set)
        for host in usable_set:
            self.usable_hosts[host] = candidates2[host]
        # for some odd reason, the above ping doesn't work when loopback.  Go figure
        self.usable_hosts[self.referencehost_obj.name] = self.referencehost_obj  # he gets left out

        # are the other hosts on different subnets?
        self.isrouted = False
        for source_interface in self.referencehost_obj.nics.keys():
            if len(numnets[source_interface]) > 1:
                self.isrouted = True
        # are there more than one subnet on this host?
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

        # do we have both IB and ETH interfaces?
        if len(self.link_types) > 1:
            self.mixed_networking = True
        else:
            self.mixed_networking = False

        # mixed networking looks routed.
        #if self.isrouted and not self.mixed_networking:
            # find gateways with "ip route get 8.8.8.8 oif enp2s0"
        #print("Exploring Gateways")  # figure out what the gateways are...
        get_gateways(self.usable_hosts, self.ssh_client.host, self.ssh_client.user, self.ssh_client.password)


def scan_hosts(reference_hostname):
    """
    scan for STEM-mode Weka hosts
    :param hostname: str
    :return: a dict containing the valid STEMHost objects
    """
    stem_beacons = beacon_hosts(reference_hostname)
    # valid_hosts = find_valid_hosts(reference_hostname, stem_beacons)
    hostgroup = WekaHostGroup(reference_hostname, stem_beacons)
    return hostgroup
