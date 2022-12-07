################################################################################################
# Logic
################################################################################################
import math
from logging import getLogger

log = getLogger(__name__)


class Cores():
    def __init__(self, total_cores, num_drives, MCB):
        # set default values on init
        self.MCB = MCB
        self.total = total_cores
        self.usable = total_cores - 5
        self.num_actual_drives = num_drives
        self.fe = 2     # default to 2 FE cores per server
        if self.usable > 19 and not self.MCB:    # single container can only have 19 cores max
            self.usable = min(19, self.total)
            log.debug(f'Host has {total_cores}, but without MCB, we can only use {self.usable}')
        else:
            self.usable = self.total - 5    # leave 5 cores for OS
        if num_drives > 8 and not MCB:
            self.drives = math.ceil(num_drives/2)
        else:
            self.drives = num_drives
        self.compute = 0    # will be determined in self.recalculate()
        self.recalculate()

    def __str__(self):
        return (
            f"cores: total={self.total}, usable={self.usable}, fe={self.fe}, drives={self.drives}, compute={self.compute}")

    def recalculate(self):
        if self.usable > 19 and not self.MCB:    # single container can only have 19 cores max
            self.usable = min(19, self.total)
        #else:
        #    self.usable = self.total - 5    # leave 5 cores for OS
        if self.drives > 8 and not self.MCB:      # make sure they make sane decisions? or just warn them?
            self.drives = math.ceil(self.drives/2)  # maybe should be a warning?
        self.compute = self.usable - self.fe - self.drives
        if self.compute < 0:
            # invalid specification
            self.__init__(self.total, self.num_actual_drives, self.MCB) # re-initialize
            #self.compute = 1
            #self.fe = 1
            #self.drives = 1
            #if self.usable < 3:
            #    self.usable = 3


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
