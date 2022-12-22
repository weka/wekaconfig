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
        host_names, host_ips = self._host_names()
        result = 'create ' + ' '.join(host_names) + ' --join-ips=' + ','.join(host_ips)
        return result

    def _host_names(self): 	# sets what the hostids will/should be
        host_names = list()
        host_ips = list()
        hostid = 0
        for hostname, host in sorted(self.config.selected_hosts.items()):
            host_names.append(hostname)
            host.host_id = hostid
            hostid += 1

            this_hosts_ifs = set()
            count = 0
            for interface in self.config.selected_dps:
                iplist = self.config.target_hosts.pingable_ips[interface]  # list of ips accessible via the interface
                for host_int, nic in host.nics.items():
                    if nic in iplist:
                        this_hosts_ifs.add(nic)

            temp = str()
            for nic in this_hosts_ifs:
                if count > 0:
                    if self.config.HighAvailability:
                        temp += '+'
                    else:
                        continue  # not HA, but has more than one NIC on the same network
                temp += nic.ip.exploded
                count += 1
            #temp += ','
            host_ips.append(temp)
            temp = str()
        return host_names, host_ips

    def _create_old(self):  # old version
        output = 'create '
        # hostnames
        hostid = 0
        for hostname, host in sorted(self.config.selected_hosts.items()):
            output += hostname + ' '
            host.host_id = hostid
            hostid += 1

        # host-ips
        # what if ha/non-ha and same subnet?   They'll all show up in one "network"
        # if self.config.HighAvailability:
        output += "--host-ips="
        for hostname, host in sorted(self.config.selected_hosts.items()):
            this_hosts_ifs = set()
            count = 0
            for interface in self.config.selected_dps:
                iplist = self.config.target_hosts.pingable_ips[interface]  # list of ips accessible via the interface
                for host_int, nic in host.nics.items():
                    if nic in iplist:
                        this_hosts_ifs.add(nic)

            for nic in this_hosts_ifs:
                if count > 0:
                    if self.config.HighAvailability:
                        output += '+'
                    else:
                        continue  # not HA, but has more than one NIC on the same network
                output += nic.ip.exploded
                count += 1
            output += ','

        result = output[:-1] if output[-1] == ',' else output
        return result

    # returns a list of strings
    def _get_nics(self, hostname):    # for MCB... need a list of nics for a host
        #base = 'host net add '
        # host_id = 0
        result = list()
        host = self.config.selected_hosts[hostname]
        this_hosts_ifs = set()
        for interface in self.config.selected_dps:
            iplist = self.config.target_hosts.pingable_ips[interface]  # list of ips accessible via the interface
            for host_int, nic in host.nics.items():
                if nic in iplist:
                    this_hosts_ifs.add(nic)

        for nic in sorted(list(this_hosts_ifs)):
            #if nic.gateway is not None:
            #    gateway = f"--gateway={nic.gateway}"
            #else:
            #    gateway = ''
            #thishost = f"{base} {host.host_id} {nic.name} --netmask={nic.network.prefixlen} {gateway}"
            #fullname = f"{nic.name}/{nic.network.prefixlen}"
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
            this_hosts_ifs = set()
            for interface in self.config.selected_dps:
                iplist = self.config.target_hosts.pingable_ips[interface]  # list of ips accessible via the interface
                for host_int, nic in host.nics.items():
                    if nic in iplist:
                        this_hosts_ifs.add(nic)

            for nic in sorted(list(this_hosts_ifs)):
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
        hosts_names_string = ' '.join(host_names)
        #hosts_ips_string = ','.join(host_ips)
        create_command = 'sudo weka cluster create ' + ' '.join(host_names) + ' --host-ips=' + ','.join(host_ips) + NL
        with file as fp:
            fp.write('# /usr/bin/bash' + NL)
            fp.write(NL)
            fp.write('# NOTE this is an experimental feature, and this script may not be correct' + NL)
            fp.write('# you should manually verify that it will do what you want/expect' + NL)
            fp.write(NL)
            #fp.write("HOSTS=" + hosts_names_string + NL)
            #fp.write('echo $HOSTS |tr " " "\n" | xargs -P8 -I{}  scp ./resources_generator.py {}:/tmp/' + NL)
            #fp.write('echo $HOSTS |tr " " "\n" | xargs -P8 -I{}  ssh {} "weka local stop; weka local rm -f default"'
            #         + NL)
            #echo $HOSTS |tr " " "\n" | xargs -P8 -I{}  ssh {} /tmp/resources_generator.py -f --path /tmp
            #      --net ens6np0 --compute-dedicated-cores 11 --drive-dedicated-cores 6 --frontend-dedicated-cores 2
            #      --compute-memory 96GiB
            #fp.write('echo $HOSTS |tr " " "\n" | xargs -P8 -I{}  ssh {} /tmp/resources_generator.py -f --path /tmp ')
            for host in host_names:  # not sure
                # run resources generator on each host
                fp.write(f"echo Running Resources generator on host {host}" + NL)
                fp.write(f'sudo scp ./resources_generator.py {host}:/tmp/' + NL)
                fp.write(f'sudo ssh {host} "weka local stop; weka local rm -f default"' + NL)
                fp.write(f'sudo ssh {host} /tmp/resources_generator.py -f --path /tmp --net')
                net_names = self._get_nics(host)
                for name in net_names:
                    fp.write(f" {name}")

                cores = self.config.selected_cores
                #thishost = base + str(host.host_id) + ' ' + str(cores.usable) + ' --frontend-dedicated-cores ' + \
                #           str(cores.fe) + ' --drives-dedicated-cores ' + str(cores.drives)

                fp.write(f' --compute-dedicated-cores {cores.usable - cores.drives - cores.fe}') # needs update?
                fp.write(f' --drive-dedicated-cores {cores.drives}')
                fp.write(f' --frontend-dedicated-cores {cores.fe}')
                if hasattr(self.config, "memory"):
                    fp.write(f' --compute-memory {self.config.memory}GiB')
                fp.write(NL)
                # probably need to look how many containers of each type it created and note that in the host
                # so we can be sure to 'weka local setup' all of them - not missing any

                # start DRIVES container
                fp.write(f"echo Starting Drives container on host {host}" + NL)
                fp.write(f'sudo ssh {host} "weka local setup host --name drives0 --resources-path /tmp/drives0.json"' + NL)
                         #'--join-ips=' + ','.join(host_ips) + NL)

            # create cluster
            fp.write(NL)
            fp.write(create_command)
            fp.write("sleep 60 " + NL)
            fp.write(NL)

            # create compute container
            for host in host_names:  # not sure
                fp.write(f"echo Starting Compute container on host {host}" + NL)
                fp.write(f'sudo ssh {host} weka local setup host --name compute0 --resources-path /tmp/compute0.json ' +
                         f'--join-ips=' + ','.join(host_ips) + NL)
            # add drives
            fp.write(NL)
            for item in self._drive_add():
                fp.write(WEKA_CLUSTER + item + NL)
            fp.write(NL)

            fp.write(WEKA_CLUSTER + self._parity() + NL)
            fp.write(WEKA_CLUSTER + self._hot_spare() + NL)
            cloud = self._cloud()
            if cloud is not None:
                fp.write(WEKA + cloud + NL)
            name = self._name()
            if name is not None:
                fp.write(WEKA_CLUSTER + name + NL)

            # start-io
            # start FEs
            fp.write(NL)
            for host in host_names:  # not sure
                fp.write(f"echo Starting Front container on host {host}" + NL)
                fp.write(f'sudo ssh {host} weka local setup host --name frontend0 --resources-path /tmp/frontend0.json ' +
                         f'--join-ips=' + ','.join(host_ips) + NL)

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
            # fp.write("sleep 60\n")
            # fp.write(WEKA_CLUSTER + self._start_io() + NL) # won't start without license in 3.14+

    def dump(self, file):
        pass

    def load(self, file):
        pass
