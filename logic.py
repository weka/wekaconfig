################################################################################################
# Logic
################################################################################################
import math
from logging import getLogger

log = getLogger(__name__)


class Cores:
    def __init__(self, total_cores, num_drives, MCB):
        # set default values on init
        self.MCB = MCB
        self.total = total_cores
        self.num_actual_drives = num_drives
        self.protocols = False
        self.proto_primary = False
        self.drives_bias = False
        self.res_os = 2  # reserved for OS
        self.res_proto = 0  # reserved for protocols
        self.fe = 2  # a reasonable default
        self.drives = num_drives    # start with 1:1 ratio
        self.compute = 0    # will recalc
        self.usable = 0  # will recalc
        self.used = 0
        self.drives_reduced = False

        # if self.total > 24:
        #    self.res_proto = 6  # reserved for Protocol containers
        #    self.fe = 4  # reserved for FE cores
        # else:
        #    self.res_proto = 3  # reserved for Protocol containers
        #    self.fe = 2  # reserved for FE cores

        # self.reserved_cores = self.res_os + self.res_proto
        # self.usable = total_cores - self.reserved_cores

        # if self.usable > 19 and not self.MCB:    # single container can only have 19 cores max
        #    self.usable = min(19, self.total)
        #    log.debug(f'Host has {total_cores}, but without MCB, we can only use {self.usable}')
        # else:
        #    self.usable = self.total - self.reserved_cores
        # if num_drives > 8 and not MCB:
        #    self.drives = math.ceil(num_drives/2)
        # else:
        #    self.drives = num_drives
        # self.compute = 0    # will be determined in self.recalculate()
        self.calculate()

    def __str__(self):
        return (
            f"cores: total={self.total}, usable={self.usable}, fe={self.fe}, drives={self.drives}, compute={self.compute}")

    # auto-calculate cores allocations
    def calculate(self):
        # sanity, in case user changed the total number of cores
        if self.protocols:
            if self.proto_primary:
                self.res_proto = 6  # if protocol is primary method, add 2 more cores
            else:
                self.res_proto = 4  # reserve at least 4 cores for protocols
        else:
            self.res_proto = 0  # no protocols?  Don't reserve any cores
        # usable cores is the total minus reserved cores - the number of cores for fe, compute, drives
        self.usable = self.total - self.res_proto - self.res_os
        if not self.MCB:
            if self.usable > 19:    # single container can only have 19 cores max
                self.usable = min(19, self.total)
            if self.drives > 8:      # SBC can't do 1:1 drives cores > 8 (not enough compute)
                self.drives = math.ceil(self.drives/2)  # maybe should be a warning?
        self.compute = self.usable - self.fe - self.drives

        if self.compute > 3 * self.drives:  # too many compute cores
            self.compute = 3 * self.drives
        elif self.compute < 2 * self.drives:  # too few compute cores
            self.drives = math.ceil(self.num_actual_drives / 2)
            # self.compute = self.drives * 2
            # if self.drives + self.compute + self.fe > self.usable:
            #    self.drives = math.ceil(self.num_actual_drives / 3)
            self.drives_reduced = True
            self.calculate()  # recurse?

        self.used = self.fe + self.drives + self.compute

        if self.compute < 0 or self.drives < 1:
            # invalid specification
            self.__init__(self.total, self.num_actual_drives, self.MCB) # re-initialize

    # re-calculate after editing (user-override)
    def recalculate(self):
        self.used = self.fe + self.drives + self.compute
        if self.used > self.usable:
            self.calculate()


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
