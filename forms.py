################################################################################################
# Forms
################################################################################################

import npyscreen

import logic
from widgets import UsableCoresWidget, ComputeCoresWidget, FeCoresWidget, DrivesCoresWidget, \
                    NameWidget, DataWidget, ParityWidget
from logic import Cores

movement_help = """Cursor movement:
    arrow keys: up, down, left, right - move between and within fields
    Space, Enter: select item
    Tab: move to next field
    """

class CancelNextForm(npyscreen.ActionFormV2):
    OK_BUTTON_TEXT = "Next"
    CANCEL_BUTTON_TEXT = "Cancel"

    def __init__(self, *args, **keywords):
        super(CancelNextForm, self).__init__(*args, **keywords)


class PrevNextForm(npyscreen.ActionFormV2):
    OK_BUTTON_TEXT = "Next"
    CANCEL_BUTTON_TEXT = "Prev"

    def __init__(self, *args, **keywords):
        super(PrevNextForm, self).__init__(*args, **keywords)


class PrevDoneForm(npyscreen.ActionFormV2):
    OK_BUTTON_TEXT = "Done"
    CANCEL_BUTTON_TEXT = "Prev"

    def __init__(self, *args, **keywords):
        super(PrevDoneForm, self).__init__(*args, **keywords)


class SelectCores(PrevDoneForm):
    def __init__(self, *args, **kwargs):
        help = """Select the number of FE, COMPUTE, and DRIVES cores for your cluster.\n\n"""
        help = help + movement_help
        super(SelectCores, self).__init__(*args, help=help, **kwargs)

    def create(self):
        self.title1 = self.add(npyscreen.FixedText, value="Host Configuration Reference",
                                    color='NO_EDIT',
                                    editable=False)
        self.total_cores = self.add(npyscreen.TitleFixedText, fieldname="cores",
                                    name="  Cores per host:",
                                    labelColor='NO_EDIT',
                                    use_two_lines=False, editable=False,
                                    begin_entry_at=19)
        self.total_drives = self.add(npyscreen.TitleFixedText, fieldname="drives",
                                     name=" Drives per host:",
                                     labelColor='NO_EDIT',
                                     use_two_lines=False, editable=False,
                                     begin_entry_at=19)
        self.num_hosts_field = self.add(npyscreen.TitleFixedText, fieldname="num_hosts",
                                     name=" Number of hosts:",
                                     labelColor='NO_EDIT',
                                     use_two_lines=False, editable=False,
                                     begin_entry_at=19)
        self.nextrely += 2 # skip 2 lines
        self.usable_cores = self.add(UsableCoresWidget, fieldname="usable",
                                     name="Total Weka Cores:",
                                     use_two_lines=False,
                                     begin_entry_at=19)
        self.nextrely += 1 # skip a line
        self.fe_cores = self.add(FeCoresWidget, fieldname="fe",
                                     name="        FE Cores:",
                                     use_two_lines=False,
                                     begin_entry_at=19)
        self.drives_cores = self.add(DrivesCoresWidget, fieldname="drives",
                                     name="    DRIVES Cores:",
                                     use_two_lines=False,
                                     begin_entry_at=19)
        self.compute_cores = self.add(ComputeCoresWidget, fieldname="compute",
                                      name="   COMPUTE Cores:",
                                      use_two_lines=False,
                                      begin_entry_at=19)
        self.nextrely += 1
        self.name_field = self.add(NameWidget, fieldname="clustername",
                                      name="    Cluster Name:",
                                      use_two_lines=False,
                                      begin_entry_at=19)
        self.nextrely += 1
        self.data_field = self.add(DataWidget, fieldname="data",
                                      name="     Data Drives:",
                                      use_two_lines=False,
                                      begin_entry_at=19)
        self.parity_field = self.add(ParityWidget, fieldname="parity",
                                      name="   Parity Drives:",
                                      use_two_lines=False,
                                      begin_entry_at=19)

    def beforeEditing(self):
        PA = self.parentApp
        if PA.selected_cores is None:
            self.num_cores = self.analyse_cores()
            self.num_drives = self.analyse_drives()
            self.parentApp.selected_cores = Cores(self.num_cores, self.num_drives)

        self.parentApp.selected_cores.recalculate()
        self.total_cores.set_value(str(self.num_cores))
        self.total_drives.set_value(str(self.num_drives))
        self.num_hosts_field.set_value(str(len(PA.selected_hosts)))
        self.usable_cores.set_value(str(PA.selected_cores.usable))
        self.fe_cores.set_value(str(PA.selected_cores.fe))
        self.compute_cores.set_value(str(PA.selected_cores.compute))
        self.drives_cores.set_value(str(PA.selected_cores.drives))

        self.name_field.set_value(PA.clustername)
        if PA.datadrives is None or \
                (PA.datadrives + PA.paritydrives) > len(PA.selected_hosts):
            PA.datadrives = len(PA.selected_hosts) - 2
            PA.paritydrives = 2

        self.data_field.set_value(str(PA.datadrives))
        self.parity_field.set_value(str(PA.paritydrives))

    def on_ok(self):
        self.parentApp.selected_cores.usable = int(self.usable_cores.value)
        self.parentApp.selected_cores.fe = int(self.fe_cores.value)
        self.parentApp.selected_cores.compute = int(self.compute_cores.value)
        self.parentApp.selected_cores.drives = int(self.drives_cores.value)
        self.parentApp.clustername = self.name_field.value
        self.parentApp.datadrives = int(self.data_field.value)
        self.parentApp.paritydrives = int(self.parity_field.value)
        # The next two lines terminate the app cleanly, so we should generate the config
        self.parentApp.setNextForm(None)
        self.parentApp.cleanexit = True

    def on_cancel(self):
        self.parentApp.switchFormPrevious()  # go to previous screen; they hit 'Prev'
        # self.pressed = "PREV"  # actually Prev

    def analyse_cores(self):
        # let's gather together the info
        host_cores = dict()
        for hostname in self.parentApp.selected_hosts:
            host_cores[hostname] = self.parentApp.target_hosts[hostname].num_cores

        # are they all the same?
        reference_cores = 0
        errors = False
        for cores in host_cores.values():
            if reference_cores == 0:
                reference_cores = cores
                continue
            else:
                if cores != reference_cores:
                    # Error!   hosts have different number of cores!
                    errors = True
                    break

        if errors:
            # make noise
            npyscreen.notify_confirm("The hosts are not homogenous; they have different numbers of cores.",
                                     title="Error", form_color='STANDOUT', wrap=True, editw=1)

        return reference_cores

    def analyse_drives(self):
        # let's gather together the info
        num_drives = dict()
        for hostname in self.parentApp.selected_hosts:
            num_drives[hostname] = len(self.parentApp.target_hosts[hostname].drives)

        reference_drives = 0
        errors = False
        for drives in num_drives.values():
            if reference_drives == 0:
                reference_drives = drives
                continue
            else:
                if drives != reference_drives:
                    errors = True
                    break
        if errors:
            # make noise
            npyscreen.notify_confirm("The hosts are not homogenous; they have different numbers of drives.",
                                     title="Error", form_color='STANDOUT', wrap=True, editw=1)

        return reference_drives

class Hosts(npyscreen.TitleMultiSelect):
    def when_value_edited(self):
        parent = self.parent
        #PA = parent.parentApp
        parent.num_hosts_field.set_value('  '+str(len(parent.hosts_field.value)))
        parent.num_hosts_field.display()


class Networks(npyscreen.TitleMultiSelect):
    def when_value_edited(self):
        value = self.parent.dataplane_networks.value
        nets = self.parent.nets
        PA = self.parent.parentApp
        PA.selected_dps = list()  # clear the list
        for index in self.parent.dataplane_networks.value:
            # save the IPv4Network objects corresponding to the selected items
            PA.selected_dps.append(self.parent.nets[index])
        self.parent.analyze_networks()
        PA.possible_hosts, PA.excluded_hosts = logic.filter_hosts(PA.selected_dps, PA.target_hosts)
        PA.sorted_hosts = sorted(PA.possible_hosts.keys())  # list of names, not STEMHost objects
        PA.hosts_value = list(range(0, len(PA.sorted_hosts)))
        if hasattr(self.parent, "hosts_field"):
            self.parent.hosts_field.set_value(PA.hosts_value)
            self.parent.hosts_field.set_values(sorted(PA.sorted_hosts))
            #self.parent.hosts_field.display()
        self.parent.num_hosts_field.set_value('  ' + str(len(PA.hosts_value)))
        self.parent.display()

    def safe_to_exit(self):
        pass
        if len(self.parent.parentApp.selected_dps) == 0:
            return False
        return True

class SelectDPNetworks(CancelNextForm):
    def __init__(self, *args, **kwargs):
        self.help = """Select the hosts that will be in your cluster.\n\n"""
        self.help = self.help + movement_help
        super(SelectDPNetworks, self).__init__(*args, help=self.help, **kwargs)

    def create(self):
        self.sorted_hosts = list()
        self.possible_dps = self.guess_networks(self.parentApp.target_hosts)
        # what happens when there's only 1 possible dp network?
        self.dataplane_networks = self.add(Networks, fieldname="networks",
                                   scroll_exit=True, # allow them to exit using arrow keys
                                   max_height=15,    # not too big - need room below for next field
                                   use_two_lines=True, # input fields start on 2nd line
                                   rely=2, # put it high on the screen
                                   max_width=38, # leave room to the right for hosts entry
                                   begin_entry_at=2, # make the list under the title
                                   name='Select DP Networks:',  # label/title
                                   #values=["255.255.255.255/32 - 200 Gbps"]) # testing
                                   values=self.possible_dps)

        self.num_hosts_field = self.add(npyscreen.TitleFixedText, fieldname="num_hosts", name="Number of Hosts:",
                                    labelColor='NO_EDIT',
                                    use_two_lines=False, editable=False, max_width=22)
        self.hosts_field = self.add(Hosts, fieldname="hosts",
                                    scroll_exit=True,  # allow them to exit using arrow keys
                                    use_two_lines=True,  # input fields start on 2nd line
                                    rely=2,  # put it high on the screen
                                    relx=39, # place to the right of Networks (above)
                                    begin_entry_at=2,  # make the list under the title
                                    name='Select Hosts:')
                                    #values=["01234567890123456789012345678901234567890123456789", # testing
                                    #        "          1         2         3         4"] ) # testing

    def on_ok(self):
        """
        if len(self.dataplane_networks.value) == 0:
            # they didn't select any
            npyscreen.notify_wait("You must select at least one dataplane network", title='ERROR')
            self.parentApp.setNextForm("SelectNetworks")
            return
        self.parentApp.selected_dps = list()  # clear the list
        for index in self.dataplane_networks.value:
            # save the IPv4Network objects corresponding to the selected items
            self.parentApp.selected_dps.append(self.nets[index])
        self.analyze_networks()
        self.parentApp.possible_hosts, self.parentApp.excluded_hosts = logic.filter_hosts(self.parentApp.selected_dps,
                                                                 self.parentApp.target_hosts)
        self.parentApp.sorted_hosts = sorted(self.parentApp.possible_hosts.keys())  # list of names, not STEMHost objects
        self.parentApp.hosts_value = list(range(0, len(self.parentApp.sorted_hosts)))
        self.parentApp.setNextForm("SelectCores")
        """
        PA = self.parentApp
        PA.selected_hosts = dict()  # toss any old values
        if len(self.hosts_field.value) < 5:
            # they didn't select any
            npyscreen.notify_wait("You must select at least 5 hosts", title='ERROR')
            return
        for index in self.hosts_field.value:  # an index into the orig list, ie: [0,2,4,6,7]
            PA.selected_hosts[PA.sorted_hosts[index]] = PA.possible_hosts[PA.sorted_hosts[index]]

        PA.setNextForm("SelectCores")

    def on_cancel(self):
        # self.pressed = "PREV"
        self.parentApp.setNextForm(None)  # prev on this form will exit program

    def analyze_networks(self):
        """
            There can be 2 types of HA network - routed and unrouted (same subnet).
            unrouted (same subnet) is most common

            This will make a list (dataplane_nics) in the host object for later reference,
            BUT IS only used during command generation.  Shouldn't it be used to select hosts?
        """
        parent = self.parentApp
        may_be_ha = False
        for net in parent.selected_dps:
            for hostname, hostobj in parent.target_hosts.items():
                hostobj.dataplane_nics = dict()  # reset the list every time, in case it changed
                for iname, interfaceobj in hostobj.nics.items():
                    if interfaceobj.network == net:
                        if net not in hostobj.dataplane_nics:
                            hostobj.dataplane_nics[net] = [interfaceobj]
                        else:
                            hostobj.dataplane_nics[net].append(interfaceobj)
                            # may_be_ha = True  # it could be an HA network

    def guess_networks(self, hostlist):
        # make a unique list of networks
        self.nets = list()
        output = list()
        for host in hostlist.values():
            for iface in host.nics.values():
                # network = ipaddress.IPv4Network(f"{iface['ip4']}/{iface['mask']}", strict=False)
                network = iface.network
                if network not in self.nets:
                    self.nets.append(network)
                    output.append(f"{iface.type}: {network} - {int(iface.speed / 1000)} Gbps")

        return output


