################################################################################################
# Weka Specific Code
################################################################################################
import ipaddress
import socket
import sys
import time

from wekalib.exceptions import NewConnectionError, LoginError, CommunicationError
from wekalib.wekaapi import WekaApi


class WekaInterface(ipaddress.IPv4Interface):
    def __init__(self, linklayer, name, address, speed):
        self.type = linklayer
        self.name = name
        self.speed = speed
        super(WekaInterface, self).__init__(address)


class STEMHost(object):
    def __init__(self, name, info_hw):
        self.name = name
        self.num_cores = len(info_hw['cores'])
        self.cpu_model = info_hw['cores'][0]['model']
        self.drives = dict()
        self.nics = dict()
        self.version = info_hw['version']
        self.info_hw = info_hw  # save a copy in case we need it
        self.dataplane_nics = dict()

        for drive in info_hw['disks']:
            if drive['type'] == "DISK" and not drive['isRotational'] and not drive['isMounted'] and \
                    len(drive['pciAddr']) > 0:
                self.drives[drive['devPath']] = drive['pciAddr']

        for net_adapter in info_hw['net']['interfaces']:
            if (4000 < net_adapter['mtu'] < 10000) and len(net_adapter['ip4']) > 0:
                details = self.find_interface_details(net_adapter['name'])
                if details['validationCode'] == "OK" and details['linkDetected']:
                    self.nics[net_adapter['name']] = \
                        WekaInterface(net_adapter['linkLayer'],
                                      details['interface_alias'],
                                      f"{net_adapter['ip4']}/{net_adapter['ip4Netmask']}",
                                      details['speedMbps'])

    def find_interface_details(self, iface):
        for eth in self.info_hw['eths']:
            if eth['interface_alias'] == iface:
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


def beacon_hosts(host):
    try:
        api = WekaApi(host, scheme="http", verify_cert=False)
    except NewConnectionError:
        print(f"ERROR: Unable to contact host '{host}'")
        sys.exit(1)

    try:
        host_status = api.weka_api_command("status", parms={})
    except LoginError:
        print(f"{host}: Login failure.  Is this host already part of a cluster?")
        sys.exit(1)
    except CommunicationError:
        print(f"{host}: Unable to communicate with {host}")
        sys.exit(1)
        # long-term, ask for admin password so we can reset/reconfigure the cluster

    if host_status['is_cluster']:
        print(f"host {host} is already part of a cluster")
        sys.exit(1)

    beacons = api.weka_api_command("cluster_list_beacons", parms={})
    # pprint(beacons)   # a dict of {ipaddr:hostname}

    stem_beacons = dict()
    for ip, hostname in beacons.items():
        if hostname not in stem_beacons:
            stem_beacons[hostname] = [ip]
        else:
            stem_beacons[hostname].append(ip)

    return stem_beacons


def find_valid_hosts(beacons):
    good_hosts = dict()
    errors = False
    for host in beacons:
        if not resolve_hostname(host):
            print(f"Host {host} does not resolve.  Is it in DNS/hosts?")
            errors = True
            continue

        host_api = WekaApi(host, scheme="http", verify_cert=False)
        try:
            machine_info = host_api.weka_api_command("machine_query_info", parms={})
        except LoginError:
            print(f"host {host} failed login?")
            errors = True
            continue
        except CommunicationError:
            print(f"Error communicating with host {host}")
            errors = True
            continue

        # pprint(machine_info)
        print(f"Host {host} is a STEM-mode instance running release {machine_info['version']}")
        good_hosts[host] = STEMHost(host, machine_info)

    if errors:
        print("Some STEM-mode hosts could not be contacted.  Are they in DNS?")
        time.sleep(5.0)
    return good_hosts


def scan_hosts(host):
    stem_beacons = beacon_hosts(host)
    valid_hosts = find_valid_hosts(stem_beacons)
    return valid_hosts
