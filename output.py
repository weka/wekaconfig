################################################################################################
# Output Utility routines
################################################################################################

from logging import getLogger

log = getLogger(__name__)


class WekaCluster(object):
    def __init__(self, config):
        self.config = config
        # figure out everything here, and just have output routines?
        # OR have each output routine figure out what it needs?

    def _create(self):
        output = 'create '
        # hostnames
        hostid = 0
        for hostname, host in sorted(self.config.selected_hosts.items()):
            output += hostname + ' '
            host.host_id = hostid
            hostid += 1

        # host-ips
        #if self.config.HighAvailability:
        output += "--host-ips="
        for hostname, host in sorted(self.config.selected_hosts.items()):
            this_hosts_ifs = set()
            count = 0
            for interface in self.config.selected_dps:
                iplist = self.config.target_hosts.pingable_ips[interface] # list of ips accessible via the interface
                for host_int, nic in host.nics.items():
                    if nic in iplist:
                        this_hosts_ifs.add(nic)

            for nic in this_hosts_ifs:
                if count > 0:
                    output += '+'
                output += nic.ip.exploded
                count += 1
            output += ','

        result = output[:-1] if output[-1] == ',' else output
        return result

    # returns a list of strings
    def _net_add(self):
        base = 'host net add '
        # host_id = 0
        result = list()
        for hostname, host in sorted(self.config.selected_hosts.items()):
            this_hosts_ifs = set()
            for interface in self.config.selected_dps:
                iplist = self.config.target_hosts.pingable_ips[interface] # list of ips accessible via the interface
                for host_int, nic in host.nics.items():
                    if nic in iplist:
                        this_hosts_ifs.add(nic)

            for nic in list(this_hosts_ifs):
                if nic.gateway is not None:
                    gateway = f"--gateway={nic.gateway}"
                else:
                    gateway = ''
                thishost = f"{base} {host.host_id} {nic.name} --netmask={nic.network.prefixlen} {gateway}"
                result.append(thishost)

        return result

    def _drive_add(self):
        base = 'drive add '
        # host_id = 0
        result = list()
        for hostname, host in sorted(self.config.selected_hosts.items()):
            thishost = base + str(host.host_id) + ' '
            for drive in sorted(host.drives.values()):
                thishost += drive + ' '
            #thishost += '--force'  # don't force it - can overwrite boot drives!
            result.append(thishost)
            # host_id += 1
        return result

    def _host_cores(self):
        base = 'host cores '
        # host_id = 0
        result = list()
        for hostname, host in sorted(self.config.selected_hosts.items()):
            cores = self.config.selected_cores
            thishost = base + str(host.host_id) + ' ' + str(cores.usable) + ' --frontend-dedicated-cores ' + \
                       str(cores.fe) + ' --drives-dedicated-cores ' + str(cores.drives)
            # host_id += 1
            result.append(thishost)
        return result

    def _memory_alloc(self):
        base = 'host memory'
        result = list()
        for hostname, host in sorted(self.config.selected_hosts.items()):
            thishost = f'{base} {host.host_id} {self.config.memory}GB'
            result.append(thishost)
        return result

    def _dedicate(self):
        if not self.config.dedicated:
            return self._memory_alloc()
        base = 'host dedicate '
        # host_id = 0
        result = list()
        for hostname, host in sorted(self.config.selected_hosts.items()):
            thishost = base + str(host.host_id) + ' on'
            result.append(thishost)
        return result

    def _parity(self):
        base = 'update '
        data_drives = len(self.config.selected_hosts) - 2
        result = base + f"--data-drives={data_drives}" + f" --parity-drives=2"
        return result

    def _failure_domain(self):
        if self.config.auto_failure_domain:
            base = 'host failure-domain '
            # host_id = 0
            result = list()
            for hostname, host in sorted(self.config.selected_hosts.items()):
                thishost = base + str(host.host_id) + ' --auto'
                result.append(thishost)
                # host_id += 1
            return result
        else:
            return []

    def _hot_spare(self):
        return "hot-spare 1"

    def _cloud(self):
        if self.config.cloud_enable:
            return "cloud enable"
        else:
            return None

    def _name(self):
        if len(self.config.clustername) > 0:
            return f"update --cluster-name={self.config.clustername}"
        else:
            return None

    def _apply(self):
        return "host apply --all --force"

    def _start_io(self):
        return "start-io"
        pass

    def cluster_config(self, file):
        WEKA_CLUSTER = "sudo weka cluster "
        WEKA = "sudo weka "
        NL = "\n"
        with file as fp:
            fp.write(WEKA_CLUSTER + self._create() + NL)
            for item in self._net_add():
                fp.write(WEKA_CLUSTER + item + NL)
            for item in self._drive_add():
                fp.write(WEKA_CLUSTER + item + NL)
            for item in self._host_cores():
                fp.write(WEKA_CLUSTER + item + NL)
            for item in self._dedicate():
                fp.write(WEKA_CLUSTER + item + NL)
            fp.write(WEKA_CLUSTER + self._parity() + NL)
            for item in self._failure_domain():
                fp.write(WEKA_CLUSTER + item + NL)
            fp.write(WEKA_CLUSTER + self._hot_spare() + NL)
            cloud = self._cloud()
            if cloud is not None:
                fp.write(WEKA + cloud + NL)
            name = self._name()
            if name is not None:
                fp.write(WEKA_CLUSTER + name + NL)
            fp.write(WEKA_CLUSTER + self._apply() + NL)
            #fp.write("sleep 60\n")
            #fp.write(WEKA_CLUSTER + self._start_io() + NL) # won't start without license in 3.14+

    def dump(self, file):
        pass

    def load(self, file):
        pass
