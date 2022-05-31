################################################################################################
# Weka Specific Code
################################################################################################
import ipaddress
import sys
from collections import OrderedDict
from logging import getLogger

from wekapyutils.wekassh import RemoteServer, parallel

from wekalib.exceptions import LoginError, CommunicationError, NewConnectionError
from wekalib.wekaapi import WekaApi
from wekapyutils.sthreads import threaded, default_threader

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
        #self.info_hw = info_hw  # save a copy in case we need it
        self.dataplane_nics = dict()
        self.total_ramGB = self.machine_info["memory"]["total"] / 1024 / 1024 / 1024

        for drive in self.machine_info['disks']:
            if drive['type'] == "DISK" and not drive['isRotational'] and not drive['isMounted'] and \
                    len(drive['pciAddr']) > 0 and drive['type'] == 'DISK':
                # not drive['isSwap'] and \     # pukes now; no longer there in 3.13
                self.drives[drive['devName']] = drive['devPath']

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
            # if we're going to do this, we have to create the STEMHost object first, not below
            candidate = STEMHost(host)
            candidate.open_api(ip_list)

            if candidate.host_api is None:
                print(f"Unable to communicate with {host} - skipping")
                errors = True
                continue  # nope, so move on to next host

            candidate.get_machine_info()
            if candidate.machine_info is None:
                errors = True
                continue  # skip it if unable to get the info

            print(f"    Host {host} is a STEM-mode instance running release {candidate.machine_info['version']}")
            candidates[host] = candidate

        if errors:
            print("Errors communicating (api) with some hosts.")
            # time.sleep(5.0)

        # find the basis host (the one they gave us on the command line)
        if self.reference_hostname not in candidates:
            # something is amiss - the host they told us to talk to doesn't list itself as a STEM host?
            print(f"{self.reference_hostname} isn't in the list of good hosts?")
            sys.exit(1)

        self.referencehost_obj = candidates[self.reference_hostname]

        # find hosts that can cluster with reference_hostname - they pointed us at reference_hostname for a reason
        candidates2 = dict()
        for hostname, hostobj in candidates.items():
            if hostobj.version != self.referencehost_obj.version:
                print(f"host {hostname} is not running v{self.referencehost_obj.version} - ignoring")
            else:
                candidates2[hostname] = hostobj

        del candidates

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

        print("Exploring network... this may take a while")
        # make sure reference_hostname can talk to the others over the dataplane networks; narrow the list,
        # and collect details of what weka hosts we can see on each nic
        self.accessible_hosts = dict()  # a dict of {ifname:(hostname)}  (set of hostnames on the nic)
        self.pingable_ips = dict()
        numnets = dict()
        for source_interface in self.referencehost_obj.nics.keys():
            self.accessible_hosts[source_interface] = set()  # hosts by interface on the reference host
            self.accessible_hosts[source_interface].add(self.reference_hostname)  # always add this
            self.pingable_ips[source_interface] = list()
            numnets[source_interface] = set()
            for hostname, hostobj in candidates2.items():
                print(f"Looking at host {hostname}...")
                # see if the reference host can talk to the target ip on each interface
                for targetif, targetip in hostobj.nics.items():
                    if hostname == reference_hostname and source_interface == targetif:
                        self.pingable_ips[source_interface].append(
                            targetip)  # should only add the ip on the source interface?
                        continue  # not sure why, but ping fails on loopback anyway
                    ssh_out = self.ssh_client.run(f"ping -c1 -W1 -I {source_interface} {targetip.ip}")
                    if ssh_out.status == 0:
                        # we were able to ping the host!  add it to the set of hosts we can access via this IF
                        self.accessible_hosts[source_interface].add(hostobj.name)
                        self.pingable_ips[source_interface].append(targetip)
                        dataplane_hostsfile[hostname] = targetip.ip
                        if targetip.network not in numnets[source_interface]:
                            numnets[source_interface].add(targetip.network)  # note unique networks
                    else:
                        log.debug(f"From {source_interface} target {hostname}-{targetip} failed.")

        # merge the accessible_hosts sets - we need the superset for later
        usable_set = set()  # should we really be using sets here?  A dict might work easier
        self.usable_hosts = dict()  # definitive list (well, dict) of hosts
        for host_set in self.accessible_hosts.values():
            if len(usable_set) != 0 and host_set != usable_set:
                log.warning("Not all hosts are accessible from all interfaces - check network config")
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
        self.get_gateways(self.usable_hosts, reference_hostname, self.ssh_client.user, self.ssh_client.password)

        # We're done with the ssh sessions now.
        # self.ssh_client.disconnect()

    def get_gateways(self, hostlist, ref_hostname, user, password):
        clients = dict()
        host_out = dict()
        print("Searching for gateways...")
        for host, host_obj in hostlist.items():
            # open sessions to all the hosts
            #print(f"Opening ssh to {host}")
            clients[host] = RemoteServer(host)
            clients[host].user = user
            clients[host].password = password if password is not None else ""

        print(f"Opening ssh to hosts")
        parallel(clients.values(), RemoteServer.connect)

        for host, host_obj in hostlist.items():
            print(f"connection to {host} established")
            host_out[host] = dict()
            for nic, nic_obj in host_obj.nics.items():
                print(f"    Scanning {host}:{nic}")
                # note - this is asynchronous...
                nic_obj.gateway = None
                host_out[host][nic_obj] = clients[host].run(f"ip route get 8.8.8.8 oif {nic}")

        # now collect the output
        for host, host_obj in hostlist.items():
            for nic_obj, cmd_output in host_out[host].items():
                outputlines = cmd_output.stdout.split('\n')
                if len(outputlines) > 0:
                    splitlines = outputlines[0].split()
                    if splitlines[1] == 'via':  # There's a gateway!
                        nic_obj.gateway = splitlines[2]
                        print(f"    Host {host}:{nic_obj.name} has gateway {nic_obj.gateway}")
                else:
                    print(f"Error executing 'ip route get' on {host}:{nic_obj.name}:" +
                          f" return code={cmd_output.exit_code}," +
                          f" stderr={list(cmd_output.stderr)}")


#        for name, client in clients.items():
#            log.debug(f"Closing ssh to {name}")
#            client.disconnect()
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
    return hostgroup
