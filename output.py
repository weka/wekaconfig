################################################################################################
# Output Utility routines
################################################################################################
class WekaCluster(object):
    def __init__(self, config):
        self.config = config
        # figure out everything here, and just have output routines?
        # OR have each output routine figure out what it needs?

    def _create(self):
        output = 'create '
        # hostnames
        for host in self.config.selected_hosts:
            output += host + ' '

        # host-ips
        output += "--host-ips="
        for host in self.config.selected_hosts.values():
            count = 0
            for nic_list in host.dataplane_nics.values():
                for nic in nic_list:
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
        host_id = 0
        result = list()
        for host in self.config.selected_hosts.values():
            thishost = base + str(host_id) + ' '
            for nic_list in host.dataplane_nics.values():
                for nic in nic_list:
                    thishost += nic.name
                result.append(thishost)
            host_id += 1
        return result

    def _drive_add(self):
        base = 'drive add '
        host_id = 0
        result = list()
        for host in self.config.selected_hosts.values():
            thishost = base + str(host_id) + ' '
            for drive in sorted(host.drives.keys()):
                thishost += drive + ' '
            thishost += '--force'
            result.append(thishost)
            host_id += 1
        return result

    def _host_cores(self):
        base = 'host cores '
        host_id = 0
        result = list()
        for host in self.config.selected_hosts.values():
            cores = self.config.selected_cores
            thishost = base + str(host_id) + ' ' + str(cores.usable) + ' --frontend-dedicated-cores ' + \
                       str(cores.fe) + ' --drives-dedicated-cores ' + str(cores.drives)
            host_id += 1
            result.append(thishost)
        return result

    def _dedicate(self):
        base = 'host dedicate '
        host_id = 0
        result = list()
        for host in self.config.selected_hosts.values():
            host_id += 1
            thishost = base + str(host_id) + ' on'
            result.append(thishost)
        return result

    def _parity(self):
        base = 'cluster update '
        data_drives = len(self.config.selected_hosts) - 2
        result = base + f"--data-drives={data_drives}" + f" --parity-drives=2"
        return result

    def _failure_domain(self):
        base = 'host failure-domain '
        host_id = 0
        result = list()
        for host in self.config.selected_hosts.values():
            host_id += 1
            thishost = base + str(host_id) + ' --auto'
            result.append(thishost)
        return result

    def _hot_spare(self):
        return "hot-spare 1"

    def _cloud(self):
        return "cloud enable"

    def _name(self):
        return f"update --cluster-name={self.config.clustername}"

    def _apply(self):
        return "host apply --all --force"

    def _start_io(self):
        return "start-io"
        pass

    def cluster_config(self, file):
        WEKA_CLUSTER = "sudo weka cluster "
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
            fp.write(WEKA_CLUSTER + self._cloud() + NL)
            fp.write(WEKA_CLUSTER + self._name() + NL)
            fp.write(WEKA_CLUSTER + self._apply() + NL)
            fp.write("sleep 60\n")
            fp.write(WEKA_CLUSTER + self._start_io() + NL)

    def dump(self, file):
        pass

    def load(self, file):
        pass
