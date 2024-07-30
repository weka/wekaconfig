################################################################################################
# Output Utility routines
################################################################################################
import math
from logging import getLogger

log = getLogger(__name__)

SCRIPT_PREAMBLE = """#!/bin/bash

usage() {
	echo "Usage: $0 [--no-parallel]"
	echo "  Use --no-parallel to prevent parallel execution"
	exit 1
}

para() {
	TF=$1; shift
	echo $*
	$* &
	[ $TF == "FALSE" ] && { echo para waiting; wait; }
}

PARA="TRUE"

# parse args
if [ $# != 0 ]; then
	if [ $# != 1 ]; then
		usage
	elif [ $1 == "--no-parallel" ]; then
		PARA="FALSE"
	else
		echo "Error: unknown command line switch - $1"
		usage
	fi
fi

echo starting - PARA is $PARA

# ------------------ custom script below --------------
"""
PARA = 'para ${PARA} '

class WekaCluster(object):
    def __init__(self, config):
        self.config = config
        # figure out everything here, and just have output routines?
        # OR have each output routine figure out what it needs?

    def _create(self):
        output = 'create '
        host_names, host_ips = self._host_names()
        result = 'create ' + ' '.join(host_names) + ' --host-ips=' + ','.join(host_ips) + " -T infinite"
        return result

    def _host_names(self):  # sets what the hostids will/should be
        host_names = list()
        host_ips = list()
        hostid = 0
        for hostname, host in sorted(self.config.selected_hosts.items()):
            host_names.append(hostname)
            host.host_id = hostid
            hostid += 1

            # make an uber list of pingable ips
            all_pingable_ips = set()
            for iface in self.config.target_hosts.pingable_ips.values():
                all_pingable_ips.update(iface)

            host.this_hosts_ifs = set()
            count = 0
            # select the interfaces that are on the selected networks
            for name, iface in host.nics.items():
                if iface.network in self.config.selected_dps:
                    if iface in all_pingable_ips:  # list of ips accessible
                        host.this_hosts_ifs.add(iface)


            temp = str()
            for nic in host.this_hosts_ifs:
                if count > 0:
                    if self.config.HighAvailability:
                        temp += '+'
                    else:
                        continue  # not HA, but has more than one NIC on the same network
                temp += nic.ip.exploded
                count += 1
            # temp += ','
            host_ips.append(temp)
            temp = str()
        return host_names, host_ips


    # returns a list of strings
    def _get_nics(self, hostname):  # for MCB... need a list of nics for a host
        # base = 'host net add '
        # host_id = 0
        result = list()
        host = self.config.selected_hosts[hostname]

        for nic in sorted(list(host.this_hosts_ifs)):
            if nic.gateway is not None:
                fullname = f"{nic.name}/{nic.ip.exploded}/{nic.network.prefixlen}/{nic.gateway}"
            else:
                fullname = f"{nic.name}/{nic.ip.exploded}/{nic.network.prefixlen}"
            result.append(fullname)

        return result

    def _net_add(self):
        base = 'host net add '
        # host_id = 0
        result = list()
        for hostname, host in sorted(self.config.selected_hosts.items()):
            for nic in sorted(list(host.this_hosts_ifs)):
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
            for drivename, drive in sorted(host.drives.items()):
                thishost += drive['devPath'] + ' '
            # thishost += '--force'  # don't force it - can overwrite boot drives!
            result.append(thishost)
            # host_id += 1
        return result

    def _host_cores(self):
        base = 'host cores '
        # host_id = 0
        result = list()
        for hostname, host in sorted(self.config.selected_hosts.items()):
            cores = self.config.selected_cores
            thishost = base + str(host.host_id) + ' ' + str(cores.fe + cores.drives + cores.compute) + ' --frontend-dedicated-cores ' + \
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
        # data_drives = len(self.config.selected_hosts) - 2
        if self.config.datadrives > 16:
            log.error(f"ERROR: datadrives is {self.config.datadrives}?")
            self.config.datadrives = 16
        result = base + f"--data-drives={self.config.datadrives}" + f" --parity-drives={self.config.paritydrives}"
        return result

    def _failure_domain(self):
        if self.config.auto_failure_domain:
            base = 'host failure-domain '
            # host_id = 0
            result = list()
            for hostname, host in sorted(self.config.selected_hosts.items()):
                thishost = base + str(host.host_id) + ' --name ' + hostname
                result.append(thishost)
                # host_id += 1
            return result
        else:
            return []

    def _hot_spare(self):
        return f"hot-spare {self.config.hot_spares}"

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
        if self.config.Multicontainer:
            self.cluster_config_mcb(file)
        else:
            self.cluster_config_scb(file)

    def cluster_config_mcb(self, file):
        WEKA_CLUSTER = "sudo weka cluster "
        WEKA = "sudo weka "
        NL = "\n"
        host_names, host_ips = self._host_names()
        create_command = WEKA_CLUSTER + 'create ' + ' '.join(host_names) + ' --host-ips=' + ','.join(host_ips) \
                         + " -T infinite" + NL
        if self.config.weka_ver[0] == '4' and int(self.config.weka_ver[1]) >= 1:
            CONTAINER = 'container'
        else:
            CONTAINER = 'host'

        with file as fp:
            fp.write(SCRIPT_PREAMBLE + NL)

            for host in host_names:
                fp.write(f"echo Stopping weka on {host}" + NL)
                if self.config.target_hosts.candidates[host].is_reference:
                    fp.write(PARA + 'cp ./resources_generator.py /tmp/' + NL)
                    fp.write('sudo weka local stop' + NL)
                    fp.write(PARA + 'sudo weka local rm -f default' + NL)
                else:
                    fp.write(PARA + f'scp -p ./resources_generator.py {host}:/tmp/' + NL)
                    fp.write(PARA + f'ssh {host} "sudo weka local stop; sudo weka local rm -f default"' + NL)

            fp.write(NL + 'wait' + NL)
            for host in host_names:
                fp.write(f"echo Running Resources generator on host {host}" + NL)
                if self.config.target_hosts.candidates[host].is_reference:
                    fp.write(PARA + 'sudo /tmp/resources_generator.py -f --path /tmp --net')
                else:
                    fp.write(PARA + f'ssh {host} sudo /tmp/resources_generator.py -f --path /tmp --net')
                net_names = self._get_nics(host)
                for name in net_names:
                    fp.write(f" {name}")

                cores = self.config.selected_cores

                fp.write(f' --compute-dedicated-cores {cores.compute}')
                fp.write(f' --drive-dedicated-cores {cores.drives}')
                fp.write(f' --frontend-dedicated-cores {cores.fe}')

                if self.config.protocols_memory is not None:
                    fp.write(f' --protocols-memory {self.config.protocols_memory}GiB')
                fp.write(NL)

            fp.write('wait' + NL)

            # start DRIVES container
            for host in host_names:
                fp.write(f"echo Starting Drives container on server {host}" + NL)
                if self.config.target_hosts.candidates[host].is_reference:
                    fp.write(PARA + f'sudo weka local setup {CONTAINER}' +
                             f' --name drives0 --resources-path /tmp/drives0.json' + NL)
                else:
                    fp.write(PARA + f'ssh {host} "sudo weka local setup {CONTAINER}' +
                             f' --name drives0 --resources-path /tmp/drives0.json"' + NL)

            # wait for parallel commands to finish
            fp.write(NL + 'wait' + NL)

            # create cluster
            fp.write(NL)
            fp.write(create_command)
            #fp.write(NL)

            # for the remaining 'local setup container' commands, we want a comma-separated list of all host_ips
            host_ips_string = ','.join(host_ips).replace('+', ',')

            # changing versions
            WLS = 'weka local setup '
            if self.config.weka_ver[0] == '4' and int(self.config.weka_ver[1]) >= 1:
                WLSC = WLS + 'container'
            else:
                WLSC = WLS + 'host'

            # create additional drives containers, if needed
            for container in range(1, math.ceil(self.config.selected_cores.drives / 19)):
                hostid = 0
                for host in host_names:  # not sure
                    fp.write(f"echo Starting drives container {container} on host {host}" + NL)
                    if self.config.target_hosts.candidates[host].is_reference:
                        fp.write(PARA + 'sudo ' + WLSC +
                                 f' --name drives{container}' +
                                 f' --resources-path /tmp/drives{container}.json' +
                                 f' --join-ips={host_ips_string}' +
                                 f' --management-ips={host_ips[hostid].replace("+", ",")}' + NL)
                    else:
                        fp.write(PARA + f'ssh {host} sudo ' + WLSC +
                             f' --name drives{container}' +
                             f' --resources-path /tmp/drives{container}.json' +
                             f' --join-ips={host_ips_string}' +
                             f' --management-ips={host_ips[hostid].replace("+", ",")}' + NL)
                    hostid += 1

                # wait for parallel commands to finish
                fp.write('wait' + NL)

            # create compute container
            for container in range(0, math.ceil(self.config.selected_cores.compute / 19)):
                hostid = 0
                for host in host_names:  # not sure
                    fp.write(f"echo Starting Compute container {container} on host {host}" + NL)
                    if self.config.target_hosts.candidates[host].is_reference:
                        fp.write(PARA + 'sudo ' + WLSC +
                                 f' --name compute{container}' +
                                 f' --resources-path /tmp/compute{container}.json' +
                                 f' --join-ips={host_ips_string}' +
                                 f' --management-ips={host_ips[hostid].replace("+", ",")}' + NL)
                    else:
                        fp.write(PARA + f'ssh {host} sudo ' + WLSC +
                             f' --name compute{container}' +
                             f' --resources-path /tmp/compute{container}.json' +
                             f' --join-ips={host_ips_string}' +
                             f' --management-ips={host_ips[hostid].replace("+", ",")}' + NL)
                    hostid += 1

            # wait for parallel commands to finish
            fp.write('wait' + NL)

            # add drives
            fp.write(NL)
            for item in self._drive_add():
                fp.write(PARA + WEKA_CLUSTER + item + NL)
            fp.write(NL)

            # wait for parallel commands to finish
            fp.write(NL + 'wait' + NL)

            fp.write(WEKA_CLUSTER + self._parity() + NL)
            fp.write(WEKA_CLUSTER + self._hot_spare() + NL)
            cloud = self._cloud()
            if cloud is not None:
                fp.write(WEKA + cloud + NL)
            name = self._name()
            if name is not None:
                fp.write(WEKA_CLUSTER + name + NL)

            # start FEs
            fp.write(NL)
            hostid = 0
            for host in host_names:  # not sure
                fp.write(f"echo Starting Front container on host {host}" + NL)
                if self.config.target_hosts.candidates[host].is_reference:
                    fp.write(PARA + 'sudo ' + WLSC + ' --name frontend0 --resources-path /tmp/frontend0.json ' +
                             f'--join-ips={host_ips_string} --management-ips={host_ips[hostid].replace("+", ",")}' + NL)
                else:
                    fp.write(PARA +
                         f'ssh {host} sudo ' + WLSC + ' --name frontend0 --resources-path /tmp/frontend0.json ' +
                         f'--join-ips={host_ips_string} --management-ips={host_ips[hostid].replace("+", ",")}' + NL)
                hostid += 1

            # wait for parallel commands to finish
            fp.write(NL + 'wait' + NL)

            fp.write(f"echo Configuration process complete" + NL)
        pass

    def cluster_config_scb(self, file):
        WEKA_CLUSTER = "weka cluster "
        WEKA = "weka "
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
            return "host apply --all --force"
            # fp.write("sleep 60\n")
            # fp.write(WEKA_CLUSTER + self._start_io() + NL) # won't start without license in 3.14+

    def dump(self, file):
        pass

    def load(self, file):
        pass
