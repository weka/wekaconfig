################################################################################################
# Logic
################################################################################################

class Cores():
    def __init__(self, total_cores, num_drives):
        # set default values on init
        self.total = total_cores
        self.usable = total_cores - 5
        if self.usable > 19:
            self.usable = 19
        self.fe = 2
        self.drives = num_drives
        self.recalculate()

    def __str__(self):
        return (
            f"cores: total={self.total}, usable={self.usable}, fe={self.fe}, drives={self.drives}, compute={self.compute}")

    def recalculate(self):
        self.compute = self.usable - self.fe - self.drives
        if self.compute < 0:
            self.compute = 1
            self.fe = 1
            self.drives = 1
            if self.usable < 3:
                self.usable = 3

def filter_hosts(network_list, host_dict):
    """Takes a list of selected IPv4Network objects and a dict of hostname:STEMHost objects
    and returns two dicts: included and excluded hosts"""
    host_sets = dict()

    # No networks selected, so no hosts selected
    if len(network_list) == 0:
        return dict(), host_dict

    # build a set of hosts for each dataplane network
    for dp in network_list:
        host_sets[dp] = set()
        for host in host_dict.values():
            for nic in host.nics.values():
                if dp == nic.network:
                    host_sets[dp].add(host)

    # get the intersection of all the sets
    set_intersection = None
    for dp, host_set in host_sets.items():
        if set_intersection is None:
            set_intersection = host_set
        else:
            set_intersection &= host_set

    full_set = set(host_dict.values())
    excluded_hosts_list = full_set - set_intersection
    included_hosts_list = list(set_intersection)

    included_hosts = dict()
    excluded_hosts = dict()

    # turn it back into a dict
    for host in excluded_hosts_list:
        excluded_hosts[str(host)] = host
    for host in included_hosts_list:
        included_hosts[str(host)] = host

    excluded_hosts_list = list()  # make a list out of it
    for host in excluded_hosts:
        excluded_hosts_list.append(str(host))

    return included_hosts, excluded_hosts
