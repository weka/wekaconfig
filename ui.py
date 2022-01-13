################################################################################################
# User Interface Code
################################################################################################

import curses.ascii

import npyscreen as npyscreen

movement_help = """Cursor movement:
    arrow keys: up, down, left, right - move between and within fields
    Space, Enter: select item
    Tab: move to next field
    """

"""  This has been moved to npyscreen itself. ;)
class Numericfield(npyscreen.Textfield):
    def __init__(self, *args, **keywords):
        super(Numericfield, self).__init__(*args, **keywords)
        self.add_complex_handlers([(self.t_input_isdigit, self.h_addch)])
        self.remove_complex_handler(self.t_input_isprint)

    # only allows numbers to be input (ie: 0 to 9)
    def t_input_isdigit(self, inp):
        import curses
        if curses.ascii.isdigit(inp):
            return True
        else:
            return False

    def safe_to_exit(self):
        try:
            parent_widget = getattr(self, "parent_widget")
        except AttributeError:
            return True
        try:
            ste = getattr(parent_widget, "safe_to_exit")
        except AttributeError:
            return True
        return ste()


class TitleNumeric(npyscreen.TitleText):
    _entry_type = Numericfield

    def __init__(self, *args, **keywords):
        self.last_value = None
        super(TitleNumeric, self).__init__(*args, **keywords)
"""


class CoresWidgetBase(npyscreen.TitleNumeric):
    def __init__(self, *args, fieldname='', **keywords):
        self.fieldname = fieldname
        self.last_value = None
        super(CoresWidgetBase, self).__init__(*args, **keywords)

    def safe_to_exit(self):
        if len(self.value) == 0:
            npyscreen.notify_wait("Please enter a number")
            return False

        self.intval = int(self.value)

        message = self.check_value()
        if message is not None:
            npyscreen.notify_wait(message)
            return False

        self.set_values()
        self.display()
        return True

    def set_values(self):
        PA = self.parent.parentApp
        PA.selected_cores.recalculate()
        self.parent.fe_cores.set_value(str(PA.selected_cores.fe))
        self.parent.compute_cores.set_value(str(PA.selected_cores.compute))
        self.parent.drives_cores.set_value(str(PA.selected_cores.drives))

    def check_value(self):
        # override me
        pass


class UsableCoresWidget(CoresWidgetBase):
    def check_value(self):
        if self.intval not in range(1, 20):
            return "Please enter a number between 1 and 19"
        self.parent.parentApp.selected_cores.usable = self.intval
        return None


class FeCoresWidget(CoresWidgetBase):
    def check_value(self):
        PA = self.parent.parentApp
        if self.intval > PA.selected_cores.usable:
            return "Cannot exceed Usable Cores"
        elif self.intval == 0:
            return "It is recommended to use at least 1 FE core"
        self.parent.parentApp.selected_cores.fe = self.intval
        return None


class DrivesCoresWidget(CoresWidgetBase):
    def check_value(self):
        PA = self.parent.parentApp
        if self.intval > PA.selected_cores.usable:
            return "Cannot exceed Usable Cores"
        elif self.intval == 0:
            return "It is recommended to use at least 1 FE core"
        elif self.intval != PA.selected_cores.drives:
            npyscreen.notify_wait("It is recommended to use 1 core per drive")
        self.parent.parentApp.selected_cores.drives = self.intval
        return None


class ComputeCoresWidget(CoresWidgetBase):
    def check_value(self):
        PA = self.parent.parentApp

        if self.intval > PA.selected_cores.usable:
            return "Cannot exceed Usable Cores"
        elif self.intval == 0:
            npyscreen.notify_wait("It is recommended to use at least 1 Compute core")
        self.parent.parentApp.selected_cores.compute = self.intval
        return None


class DataParityBase(CoresWidgetBase):
    def check_value(self):
        PA = self.parent.parentApp
        self.clustersize = len(PA.selected_hosts)
        if self.intval > self.clustersize - 2:
            return f"The most data drives for a cluster of {self.clustersize} hosts is {self.clustersize - 2}"
        elif self.intval + PA.paritydrives > self.clustersize:
            PA.paritydrives = 2
        return self._check_value()

    def _check_value(self):
        # override me
        pass


class DataWidget(DataParityBase):
    def _check_value(self):
        if self.intval not in range(3, self.clustersize - 1):
            return f"Data drives must be between 3 and {self.clustersize - 2}"
        return None

    def set_values(self):
        PA = self.parent.parentApp
        PA.datadrives = self.intval


class ParityWidget(DataParityBase):
    def _check_value(self):
        if self.intval == 4 and self.clustersize <= 8:
            return "Parity of 4 can only be used with clusters with more than 8 hosts"
        if self.intval not in [2, 4]:
            return "Parity must be either 2 or 4"
        return None

    def set_values(self):
        PA = self.parent.parentApp
        PA.paritydrives = self.intval


class NonEmptyfield(npyscreen.Textfield):
    def __init__(self, *args, **keywords):
        super(NonEmptyfield, self).__init__(*args, **keywords)
        self.add_complex_handlers([(self.t_input_isname, self.h_addch)])
        self.remove_complex_handler(self.t_input_isprint)

    # only allows numbers to be input (ie: 0 to 9)
    def t_input_isname(self, inp):
        import curses
        if curses.ascii.isspace(inp):
            npyscreen.notify_wait("Only a-z,A-Z,0-9,-, and _ are allowed in names")
            return False
        elif curses.ascii.isalnum(inp):
            return True
        elif curses.ascii.isdigit(inp):
            return True
        elif curses.ascii.ispunct(inp):
            return True
        else:
            npyscreen.notify_wait("Only a-z,A-Z,0-9,.,-, and _ are allowed in names")
            return False


class TitleNonEmpty(npyscreen.TitleText):
    _entry_type = NonEmptyfield

    def __init__(self, *args, **keywords):
        self.last_value = None
        super(TitleNonEmpty, self).__init__(*args, **keywords)


class NameWidget(TitleNonEmpty):
    def __init__(self, *args, fieldname='', **keywords):
        self.fieldname = fieldname
        self.last_value = None
        super(NameWidget, self).__init__(*args, **keywords)
        pass

    def safe_to_exit(self):
        if len(self.value) > 0:
            return True
        else:
            npyscreen.notify_wait("Please enter a name")
            return False


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
        self.title1 = self.add(npyscreen.FixedText, value="Host Configuration", editable=False)
        self.total_cores = self.add(npyscreen.TitleFixedText, fieldname="cores", name="  Cores per host:",
                                    use_two_lines=False, editable=False, begin_entry_at=22)
        self.total_drives = self.add(npyscreen.TitleFixedText, fieldname="drives", name="  Drives per host:",
                                     use_two_lines=False, editable=False, begin_entry_at=22)
        self.nextrely += 1
        self.usable_cores = self.add(UsableCoresWidget, fieldname="usable", name="Total Cores for Weka:",
                                     use_two_lines=False, begin_entry_at=22)
        self.nextrely += 1
        self.fe_cores = self.add(FeCoresWidget, fieldname="fe", name="FE Cores:", use_two_lines=False,
                                 begin_entry_at=22)
        self.drives_cores = self.add(DrivesCoresWidget, fieldname="drives", name="DRIVES Cores:", use_two_lines=False,
                                     begin_entry_at=22)
        self.compute_cores = self.add(ComputeCoresWidget, fieldname="compute", name="COMPUTE Cores:",
                                      use_two_lines=False, begin_entry_at=22)
        self.nextrely += 1
        self.name_field = self.add(NameWidget, fieldname="clustername", name="Name of the cluster:",
                                   value="changeme", use_two_lines=False, begin_entry_at=22)
        self.nextrely += 1
        self.data_field = self.add(DataWidget, fieldname="data", name="Data Drives:",
                                   use_two_lines=False, begin_entry_at=22)
        self.parity_field = self.add(ParityWidget, fieldname="parity", name="Parity Drives:",
                                     use_two_lines=False, begin_entry_at=22)

    def beforeEditing(self):
        if self.parentApp.selected_cores is None:
            self.num_cores = self.analyse_cores()
            self.num_drives = self.analyse_drives()
            self.parentApp.selected_cores = Cores(self.num_cores, self.num_drives)

        self.parentApp.selected_cores.recalculate()
        self.total_cores.set_value(str(self.num_cores))
        self.total_drives.set_value(str(self.num_drives))
        self.usable_cores.set_value(str(self.parentApp.selected_cores.usable))
        self.fe_cores.set_value(str(self.parentApp.selected_cores.fe))
        self.compute_cores.set_value(str(self.parentApp.selected_cores.compute))
        self.drives_cores.set_value(str(self.parentApp.selected_cores.drives))

        self.name_field.set_value(self.parentApp.clustername)
        if self.parentApp.datadrives is None or \
                (self.parentApp.datadrives + self.parentApp.paritydrives) > len(self.parentApp.selected_hosts):
            self.parentApp.datadrives = len(self.parentApp.selected_hosts) - 2
            self.parentApp.paritydrives = 2

        self.data_field.set_value(str(self.parentApp.datadrives))
        self.parity_field.set_value(str(self.parentApp.paritydrives))

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


class SelectHosts(PrevNextForm):
    def __init__(self, *args, **kwargs):
        self.help = """Select the hosts that will be in your cluster.\n\n"""
        self.help = self.help + movement_help
        super(SelectHosts, self).__init__(*args, help=self.help, **kwargs)

    def create(self):
        self.selected_hosts = None

    def beforeEditing(self):
        self.possible_hosts = self.hosts_on_dp()  # list of STEMHost objects
        self.sorted_hosts = sorted(self.possible_hosts.keys())  # list of names, not STEMHost objects
        if self.selected_hosts is None:
            self.selected_hosts = self.add(npyscreen.TitleMultiSelect, scroll_exit=True, max_height=15,
                                           value=list(range(0, len(self.sorted_hosts))),
                                           name='Select Hosts:',
                                           values=self.sorted_hosts)

    def on_ok(self):
        # record what's on the screen
        self.parentApp.selected_hosts = dict()  # toss any old values
        if len(self.selected_hosts.value) < 5:
            # they didn't select any
            npyscreen.notify_wait("You must select at least 5 hosts", title='ERROR')
            return
        for index in self.selected_hosts.value:  # an index into the orig list, ie: [0,2,4,6,7]
            self.parentApp.selected_hosts[self.sorted_hosts[index]] = self.possible_hosts[self.sorted_hosts[index]]

        self.parentApp.setNextForm("SelectCores")

    def on_cancel(self):
        self.parentApp.switchFormPrevious()  # back to Prev form

    def hosts_on_dp(self):
        # dps is a list of IPv4Network objects that were selected
        dps = self.parentApp.selected_dps
        # hosts is a list of STEMHost objects that we're considering
        hosts = self.parentApp.target_hosts
        # this should ensure that all the hosts are on ALL the selected networks
        host_sets = dict()
        # build a set of hosts for each dataplane network
        for dp in dps:
            host_sets[dp] = set()
            for host in hosts.values():
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

        full_set = set(self.parentApp.target_hosts.values())
        excluded_hosts = full_set - set_intersection
        dataplane_hosts_list = list(set_intersection)
        dataplane_hosts = dict()

        # turn it back into a dict
        for host in dataplane_hosts_list:
            dataplane_hosts[str(host)] = host

        excluded_hosts_list = list()  # make a list out of it
        for host in excluded_hosts:
            excluded_hosts_list.append(str(host))
        if len(excluded_hosts) != 0:
            npyscreen.notify_confirm(f"The following hosts were excluded because they do not " +
                                     f"share all the dataplane networks selected:\n{excluded_hosts_list}",
                                     title="Attention!", form_color='STANDOUT', wrap=True, editw=1)

        return dataplane_hosts


class SelectDPNetworks(CancelNextForm):
    def __init__(self, *args, **kwargs):
        self.help = """Select the hosts that will be in your cluster.\n\n"""
        self.help = self.help + movement_help
        super(SelectDPNetworks, self).__init__(*args, help=self.help, **kwargs)

    def create(self):
        self.possible_dps = self.guess_networks(self.parentApp.target_hosts)
        self.dataplane_networks = self.add(npyscreen.TitleMultiSelect, scroll_exit=True, max_height=9,
                                           name='Select DP Networks:',
                                           values=self.possible_dps)

    def on_ok(self):
        # self.pressed = "NEXT"
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
        self.parentApp.setNextForm("Hosts")

    def on_cancel(self):
        # self.pressed = "PREV"
        self.parentApp.setNextForm(None)  # prev on this form will exit program

    def analyze_networks(self):
        """
            There can be 2 types of HA network - routed and unrouted (same subnet).
            unrouted (same subnet) is most common
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
                    output.append(f"{iface.type}: {network} - {iface.speed / 1000} Gbps")

        return output


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


class WekaConfigApp(npyscreen.NPSAppManaged):
    STARTING_FORM = "SelectNetworks"

    def __init__(self, hostlist):
        self.target_hosts = hostlist  # STEMHost objects
        self.selected_dps = list()
        self.selected_hosts = dict()
        self.selected_cores = None
        self.clustername = None
        self.datadrives = None
        self.paritydrives = None
        self.cleanexit = False

        super(WekaConfigApp, self).__init__()

    def onStart(self):
        self.addForm("SelectNetworks", SelectDPNetworks, "Weka Configurator (Networks)")
        self.addForm("Hosts", SelectHosts, "Weka Configurator (Hosts)")
        self.addForm("SelectCores", SelectCores, "Weka Configurator (Cores)")

    # on exit of application - when next form is None
    # def onCleanExit(self):
    #    print(f"selected dp networks are: {self.selected_dps}")
