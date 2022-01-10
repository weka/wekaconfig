################################################################################################
# User Interface Code
################################################################################################
import copy

import npyscreen as npyscreen
import curses.ascii

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


class UsableCoresWidget(npyscreen.TitleNumeric):
    def __init__(self, *args, fieldname='', **keywords):
        self.fieldname = fieldname
        self.last_value = None
        super(UsableCoresWidget, self).__init__(*args, **keywords)
        pass

    def safe_to_exit(self):
        if len(self.value) == 0:
            npyscreen.notify_wait("Please enter a number")
            return False
        else:
            intval = int(self.value)
        PA = self.parent.parentApp
        if intval > 19 or intval < 1:
            npyscreen.notify_wait("Please enter a number between 1 and 19")
            return False

        PA.selected_cores.usable = intval
        PA.selected_cores.recalculate()
        self.parent.fe_cores.set_value(str(PA.selected_cores.fe))
        self.parent.compute_cores.set_value(str(PA.selected_cores.compute))
        self.parent.drives_cores.set_value(str(PA.selected_cores.drives))
        self.display()
        return True


class FeCoresWidget(npyscreen.TitleNumeric):
    def __init__(self, *args, fieldname='', **keywords):
        self.fieldname = fieldname
        self.last_value = None
        super(FeCoresWidget, self).__init__(*args, **keywords)
        pass

    def safe_to_exit(self):
        if len(self.value) == 0:
            npyscreen.notify_wait("Please enter a number")
            return False
        else:
            intval = int(self.value)
        PA = self.parent.parentApp
        if intval > PA.selected_cores.usable:
            npyscreen.notify_wait("Cannot exceed Usable Cores")
            return False
        elif intval == 0:
            npyscreen.notify_wait("It is recommended to use at least 1 FE core")

        PA.selected_cores.fe = intval
        PA.selected_cores.recalculate()
        self.parent.fe_cores.set_value(str(PA.selected_cores.fe))
        self.parent.compute_cores.set_value(str(PA.selected_cores.compute))
        self.parent.drives_cores.set_value(str(PA.selected_cores.drives))
        self.display()
        return True


class DrivesCoresWidget(npyscreen.TitleNumeric):
    def __init__(self, *args, fieldname='', **keywords):
        self.fieldname = fieldname
        self.last_value = None
        super(DrivesCoresWidget, self).__init__(*args, **keywords)
        pass

    def safe_to_exit(self):
        if len(self.value) == 0:
            npyscreen.notify_wait("Please enter a number")
            return False
        else:
            intval = int(self.value)
        PA = self.parent.parentApp
        if intval > PA.selected_cores.usable:
            npyscreen.notify_wait("Cannot exceed Usable Cores")
            return False
        elif intval == 0:
            npyscreen.notify_wait("It is recommended to use at least 1 Drives core")
        elif intval != PA.selected_cores.drives:
            npyscreen.notify_wait("It is recommended to use 1 core per drive")

        PA.selected_cores.drives = intval
        PA.selected_cores.recalculate()
        self.parent.fe_cores.set_value(str(PA.selected_cores.fe))
        self.parent.compute_cores.set_value(str(PA.selected_cores.compute))
        self.parent.drives_cores.set_value(str(PA.selected_cores.drives))
        self.display()
        return True


class ComputeCoresWidget(npyscreen.TitleNumeric):
    def __init__(self, *args, fieldname='', **keywords):
        self.fieldname = fieldname
        self.last_value = None
        super(ComputeCoresWidget, self).__init__(*args, **keywords)
        pass

    def safe_to_exit(self):
        if len(self.value) == 0:
            npyscreen.notify_wait("Please enter a number")
            return False
        else:
            intval = int(self.value)
        PA = self.parent.parentApp
        if intval > PA.selected_cores.usable:
            npyscreen.notify_wait("Cannot exceed Usable Cores")
            return False
        elif intval == 0:
            npyscreen.notify_wait("It is recommended to use at least 1 Compute core")

        PA.selected_cores.compute = intval
        PA.selected_cores.drives = PA.selected_cores.usable - PA.selected_cores.fe - PA.selected_cores.compute
        # PA.selected_cores.recalculate()
        self.parent.fe_cores.set_value(str(PA.selected_cores.fe))
        self.parent.compute_cores.set_value(str(PA.selected_cores.compute))
        self.parent.drives_cores.set_value(str(PA.selected_cores.drives))
        self.display()
        return True


class CoresTextWidget(npyscreen.TitleText):
    def __init__(self, *args, fieldname='', **keywords):
        self.fieldname = fieldname
        self.last_value = None
        super(CoresTextWidget, self).__init__(*args, **keywords)

    def edit(self):
        self.last_value = copy.deepcopy(self.value)
        super(CoresTextWidget, self).edit()
        if not str.isnumeric(self.value):
            self.value = self.last_value
            self.display()
            return
        cores = int(self.value)
        if self.fieldname == "usable":
            if cores > 19:
                cores = 19  # fixed maximum
            self.parent.parentApp.selected_cores.usable = cores
            self.parent.parentApp.selected_cores.recalculate()
        else:
            if cores > self.parent.parentApp.selected_cores.usable:
                # out of range - reject value
                self.value = self.last_value
                self.display()
                return
            if self.fieldname == "fe":
                if cores <= 0 or cores > self.parent.parentApp.selected_cores.usable:
                    cores = 1  # range check

                self.parent.parentApp.selected_cores.fe = cores
                self.parent.parentApp.selected_cores.recalculate()

                # if they change fe cores higher, deduct them from the compute cores
                if self.parent.parentApp.selected_cores.compute < 0:
                    # self.parent.parentApp.selected_cores.compute = 0  # no need to do this
                    self.parent.parentApp.selected_cores.recalculate()
            elif self.fieldname == "compute":
                if cores <= 0 or cores > self.parent.parentApp.selected_cores.usable:
                    cores = 0  # range check
                self.parent.parentApp.selected_cores.compute = cores

                # if they change compute cores higher, deduct them from the fe cores?
                # self.parent.parentApp.selected_cores.recalculate()
                self.parent.parentApp.selected_cores.drives = self.parent.parentApp.selected_cores.usable - \
                                                              self.parent.parentApp.selected_cores.fe - \
                                                              self.parent.parentApp.selected_cores.compute

            elif self.fieldname == "drives":
                if cores <= 0 or cores > self.parent.parentApp.selected_cores.usable:
                    cores = 0  # range check

                self.parent.parentApp.selected_cores.drives = cores
                self.parent.parentApp.selected_cores.recalculate()

        # set self.value again
        self.parent.fe_cores.set_value(str(self.parent.parentApp.selected_cores.fe))
        self.parent.compute_cores.set_value(str(self.parent.parentApp.selected_cores.compute))
        self.parent.drives_cores.set_value(str(self.parent.parentApp.selected_cores.drives))
        self.display()
        return


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

    def safe_to_exit(self):
        return self.parent_widget.safe_to_exit()


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


class DataWidget(npyscreen.TitleNumeric):
    def __init__(self, *args, fieldname='', **keywords):
        self.fieldname = fieldname
        self.last_value = None
        super(DataWidget, self).__init__(*args, **keywords)
        pass

    def safe_to_exit(self):
        if len(self.value) == 0:
            npyscreen.notify_wait("Please enter a number")
            return False
        else:
            intval = int(self.value)
        PA = self.parent.parentApp
        clustersize = len(PA.selected_hosts)
        if intval < 3:
            npyscreen.notify_wait("The minimum number of data drives is 3")
            return False
        elif intval > clustersize - 2:
            npyscreen.notify_wait(f"The most data drives for a cluster of {clustersize} hosts is {clustersize - 2}")
            return False
        elif intval + PA.paritydrives > clustersize:
            PA.paritydrives = 2
        PA.datadrives = intval
        self.display()
        return True


class ParityWidget(npyscreen.TitleNumeric):
    def __init__(self, *args, fieldname='', **keywords):
        self.fieldname = fieldname
        self.last_value = None
        super(ParityWidget, self).__init__(*args, **keywords)
        pass

    def safe_to_exit(self):
        if len(self.value) == 0:
            npyscreen.notify_wait("Please enter a number")
            return False
        else:
            intval = int(self.value)
        PA = self.parent.parentApp
        clustersize = len(PA.selected_hosts)
        if intval == 2 or (intval == 4 and clustersize > 8):
            return True
        if intval != 2 and intval != 4:
            npyscreen.notify_wait("Parity can be 2 or 4 only")
        elif intval == 4 and clustersize < 9:
            npyscreen.notify_wait("Parity of 4 can only be used in clusters of 9 or more hosts")
        return False


class PrevNextForm(npyscreen.ActionFormV2):
    OK_BUTTON_TEXT = "Next"
    CANCEL_BUTTON_TEXT = "Prev"

    def __init__(self, *args, **keywords):
        super(PrevNextForm, self).__init__(*args, **keywords)


class Misc(PrevNextForm):
    def __init__(self, *args, **kwargs):
        help = """Name the cluster.\n\n"""
        help = help + movement_help
        super(Misc, self).__init__(*args, help=help, **kwargs)

    def create(self):
        self.name_field = self.add(NameWidget, fieldname="clustername", name="Name of the cluster:",
                                   value="changeme", use_two_lines=False, begin_entry_at=22)
        self.data_field = self.add(DataWidget, fieldname="data", name="Data Drives:",
                                   use_two_lines=False, begin_entry_at=22)
        self.parity_field = self.add(ParityWidget, fieldname="parity", name="Parity Drives:",
                                     use_two_lines=False, begin_entry_at=22)

    def beforeEditing(self):
        self.name_field.set_value(self.parentApp.clustername)
        if self.parentApp.datadrives is None:
            self.parentApp.datadrives = len(self.parentApp.selected_hosts) - 2
            self.parentApp.paritydrives = 2

        self.data_field.set_value(str(self.parentApp.datadrives))
        self.parity_field.set_value(str(self.parentApp.paritydrives))

    def afterEditing(self):
        self.parentApp.clustername = self.name_field.value
        self.parentApp.datadrives = int(self.data_field.value)
        self.parentApp.paritydrives = int(self.parity_field.value)
        if self.pressed == "NEXT":
            self.parentApp.setNextForm(None)
        else:
            self.parentApp.switchFormPrevious()  # go to previous scrreen; they hit 'Prev'

    def on_ok(self):
        self.pressed = "NEXT"  # actually Next

    def on_cancel(self):
        self.pressed = "PREV"  # actually Prev


class SelectCores(PrevNextForm):
    def __init__(self, *args, **kwargs):
        help = """Select the number of FE, COMPUTE, and DRIVES cores for your cluster.\n\n"""
        help = help + movement_help
        super(SelectCores, self).__init__(*args, help=help, **kwargs)

    def create(self):
        self.title1 = self.add(npyscreen.FixedText, value="Host Configuration", editable=False)
        self.total_cores = self.add(npyscreen.TitleFixedText, fieldname="cores", name="  Cores per host:",
                                    use_two_lines=False, editable=False, begin_entry_at=24)
        self.total_drives = self.add(npyscreen.TitleFixedText, fieldname="drives", name="  Drives per host:",
                                     use_two_lines=False, editable=False, begin_entry_at=24)
        self.nextrely += 1
        self.usable_cores = self.add(UsableCoresWidget, fieldname="usable", name="Total Cores for Weka:",
                                     use_two_lines=False, begin_entry_at=22)
        self.nextrely += 1
        self.fe_cores = self.add(FeCoresWidget, fieldname="fe", name="FE Cores:", use_two_lines=False)
        self.drives_cores = self.add(DrivesCoresWidget, fieldname="drives", name="DRIVES Cores:", use_two_lines=False)
        self.compute_cores = self.add(ComputeCoresWidget, fieldname="compute", name="COMPUTE Cores:",
                                      use_two_lines=False)

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
        # set field exit handlers so we can recalc on-the-fly

    def afterEditing(self):
        self.parentApp.selected_cores.usable = int(self.usable_cores.value)
        self.parentApp.selected_cores.fe = int(self.fe_cores.value)
        self.parentApp.selected_cores.compute = int(self.compute_cores.value)
        self.parentApp.selected_cores.drives = int(self.drives_cores.value)
        if self.pressed == "NEXT":
            self.parentApp.setNextForm("Misc")
        else:
            self.parentApp.switchFormPrevious()  # go to previous scrreen; they hit 'Prev'

    def on_ok(self):
        self.pressed = "NEXT"  # actually Next

    def on_cancel(self):
        self.pressed = "PREV"  # actually Prev

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
        # hostlist = list()
        hostlist = dict()
        for host in self.possible_hosts:
            # hostlist.append(str(host))
            hostlist[str(host)] = host  # dict of hostname:STEMHost
        # self.sorted_hosts = sorted(hostlist)    # list of names, not STEMHost objects
        self.sorted_hosts = sorted(hostlist.keys())  # list of names, not STEMHost objects
        if self.selected_hosts is None:
            self.selected_hosts = self.add(npyscreen.TitleMultiSelect, scroll_exit=True, max_height=15,
                                           value=list(range(0, len(self.sorted_hosts))),
                                           name='Select Hosts:',
                                           values=self.sorted_hosts)

    def afterEditing(self):
        if self.pressed == "NEXT":
            if len(self.selected_hosts.value) < 5:
                # they didn't select any
                npyscreen.notify_wait("You must select at least 5 hosts", title='ERROR')
                return
            for index in self.selected_hosts.value:  # an index into the orig list, ie: [0,2,4,6,7]
                # self.parentApp.selected_hosts.append(self.sorted_hosts[index])
                self.parentApp.selected_hosts[self.sorted_hosts[index]] = self.possible_hosts[self.sorted_hosts[index]]
            self.parentApp.setNextForm("SelectCores")
        else:
            self.parentApp.switchFormPrevious()  # back to Prev form

    def on_ok(self):
        self.pressed = "NEXT"

    def on_cancel(self):
        self.pressed = "PREV"

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


class SelectDPNetworks(PrevNextForm):
    def __init__(self, *args, **kwargs):
        self.help = """Select the hosts that will be in your cluster.\n\n"""
        self.help = self.help + movement_help
        super(SelectDPNetworks, self).__init__(*args, help=self.help, **kwargs)

    def create(self):
        self.possible_dps = self.guess_networks(self.parentApp.target_hosts)
        self.dataplane_networks = self.add(npyscreen.TitleMultiSelect, scroll_exit=True, max_height=9,
                                           name='Select DP Networks:',
                                           values=self.possible_dps)

    def afterEditing(self):
        # DP networks selected are self.dataplane_networks.value (a list of indices)
        if self.pressed == "NEXT":
            if len(self.dataplane_networks.value) == 0:
                # they didn't select any
                npyscreen.notify_wait("You must select at least one dataplane network", title='ERROR')
                self.parentApp.setNextForm("MAIN")
                return
            for index in self.dataplane_networks.value:
                # save the IPv4Network objects corresponding to the selected items
                self.parentApp.selected_dps.append(self.nets[index])
            self.analyze_networks()
            self.parentApp.setNextForm("Hosts")
        else:
            self.parentApp.setNextForm(None)  # prev on this form will exit program

    def on_ok(self):
        self.pressed = "NEXT"

    def on_cancel(self):
        self.pressed = "PREV"

    def analyze_networks(self):
        """
            There can be 2 types of HA network - routed and unrouted (same subnet).
            unrouted (same subnet) is most common
        """
        parent = self.parentApp
        may_be_ha = False
        for net in parent.selected_dps:
            for hostname, hostobj in parent.target_hosts.items():
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
    def __init__(self, hostlist):
        self.target_hosts = hostlist  # STEMHost objects
        self.selected_dps = list()
        self.selected_hosts = dict()
        self.selected_cores = None
        self.clustername = None
        self.datadrives = None
        self.paritydrives = None

        super(WekaConfigApp, self).__init__()

    def onStart(self):
        self.addForm("MAIN", SelectDPNetworks, "Weka Configurator (Networks)")
        self.addForm("Hosts", SelectHosts, "Weka Configurator (Hosts)")
        self.addForm("SelectCores", SelectCores, "Weka Configurator (Cores)")
        self.addForm("Misc", Misc, "Weka Configurator (Misc)")
        # self.addForm("MAIN", Misc, "Weka Configurator (Misc)")

    # on exit of application - when next form is None
    def onCleanExit(self):
        print(f"selected dp networks are: {self.selected_dps}")
