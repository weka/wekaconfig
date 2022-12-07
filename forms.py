################################################################################################
# Forms
################################################################################################
# These forms define what pages the user sees

from logging import getLogger

import wekatui

log = getLogger(__name__)

from widgets import UsableCoresWidget, ComputeCoresWidget, FeCoresWidget, DrivesCoresWidget, \
    NameWidget, DataWidget, ParityWidget, MiscWidget, WekaTitleFixedText, MemoryWidget, Networks, Hosts, \
    HighAvailability, multicontainer, SparesWidget

from logic import Cores

movement_help = """Cursor movement:
    arrow keys: up, down, left, right - move between and within fields
    Space, Enter: select item
    Tab: move to next field
    """


# base classes
class WekaActionForm(wekatui.ActionFormV2):
    def pre_edit_loop(self):
        if not self.preserve_selected_widget:
            self.editw = 0
        if not self._widgets__[self.editw].editable:
            self.find_next_editable()


class CancelNextForm(WekaActionForm):
    OK_BUTTON_TEXT = "Next"
    CANCEL_BUTTON_TEXT = "Cancel"

    def __init__(self, *args, **keywords):
        super(CancelNextForm, self).__init__(*args, **keywords)


class PrevNextForm(WekaActionForm):
    OK_BUTTON_TEXT = "Next"
    CANCEL_BUTTON_TEXT = "Prev"

    def __init__(self, *args, **keywords):
        super(PrevNextForm, self).__init__(*args, **keywords)


class PrevDoneForm(WekaActionForm):
    OK_BUTTON_TEXT = "Done"
    CANCEL_BUTTON_TEXT = "Prev"

    def __init__(self, *args, **keywords):
        super(PrevDoneForm, self).__init__(*args, **keywords)


# a form that lets the user select core configuration and data/parity and some options
class SelectCoresForm(PrevDoneForm):
    def __init__(self, *args, **kwargs):
        help = """Select the number of FE, COMPUTE, and DRIVES cores for your cluster.\n\n"""
        help = help + movement_help
        super(SelectCoresForm, self).__init__(*args, help=help, **kwargs)

    def create(self):
        self.title1 = self.add(wekatui.FixedText,
                               value="Host Configuration Reference",
                               color='NO_EDIT',
                               editable=False)
        self.total_cores_field = self.add(WekaTitleFixedText, label="Cores per host", entry_field_width=3)
        self.total_drives_field = self.add(WekaTitleFixedText, label="Drives per host", entry_field_width=3)
        self.num_hosts_field = self.add(WekaTitleFixedText, label="Number of hosts", entry_field_width=3)
        self.nextrely += 2  # skip 2 lines
        self.usable_cores_field = self.add(UsableCoresWidget, label="Total Weka Cores", entry_field_width=2)
        self.nextrely += 1  # skip a line
        self.fe_cores_field = self.add(FeCoresWidget, label="FE Cores", entry_field_width=2)
        self.drives_cores_field = self.add(DrivesCoresWidget, label="DRIVES Cores", entry_field_width=2)
        self.compute_cores_field = self.add(ComputeCoresWidget, label="COMPUTE Cores", entry_field_width=2)
        self.nextrely += 1
        self.name_field = self.add(NameWidget, label="Cluster Name", entry_field_width=32)
        self.nextrely += 1
        self.data_field = self.add(DataWidget, label="Data Drives", entry_field_width=2)
        self.parity_field = self.add(ParityWidget, label="Parity Drives", entry_field_width=2)
        self.nextrely += 1
        self.spares_field = self.add(SparesWidget, label="Hot Spares", entry_field_width=2)

        self.align_fields()

        self.misc_values = [
            "Dedicated",
            "Auto Failure Domain",
            "Cloud Enable"
        ]
        self.misc_field = self.add(MiscWidget,
                                   scroll_exit=True,  # allow them to exit using arrow keys
                                   use_two_lines=True,  # input fields start on 2nd line
                                   rely=2,  # put it high on the screen
                                   relx=39,  # place to the right of Networks (above)
                                   begin_entry_at=2,  # make the list under the title
                                   max_height=len(self.misc_values) + 1,
                                   name='Misc:',
                                   values=self.misc_values,  # field labels
                                   value=[]  # which are selected - set later
                                   )

        self.memory_field = self.add(MemoryWidget,
                                     label="RAM per Host",
                                     rely=2 + len(self.misc_values) + 2,
                                     relx=39,
                                     entry_field_width=3)

        # values=["01234567890123456789012345678901234567890123456789", # testing
        #        "          1         2         3         4"] ) # testing

    def align_fields(self):
        """align the input fields so they all start at the same X offset & right-justify the label"""

        # find how long the longest label is
        longest_label = 0
        for widget in self._widgets__:
            if wekatui.TitleText in widget.__class__.__mro__:  # is this the right type of object?
                widget.label_len = len(widget.label_widget.value)
                if widget.label_len > longest_label:
                    longest_label = widget.label_len

        entry_field_starts_at = longest_label + 1
        for widget in self._widgets__:
            if wekatui.TitleText in widget.__class__.__mro__:  # is this the right type of object?
                # move the label to the right so that they all end at the same spot
                relx_delta = longest_label - widget.label_len
                widget.set_relyx(widget.rely, widget.relx + relx_delta)
                # set where the entry field will be - note that it's relative to relx
                widget.text_field_begin_at = entry_field_starts_at - relx_delta

        # fix the field width
        for widget in self._widgets__:
            if wekatui.TitleText in widget.__class__.__mro__:  # is this the right type of object?
                widget.width = widget.text_field_begin_at + widget.entry_field_width
                widget.entry_widget.width = widget.entry_field_width + 1
                widget.entry_widget.request_width = widget.entry_field_width + 1

    def beforeEditing(self):
        PA = self.parentApp
        if PA.selected_cores is None:  # if we haven't visited this form before
            self.num_cores = self.analyse_cores()
            self.num_drives = self.analyse_drives()
            PA.selected_cores = Cores(self.num_cores, self.num_drives, PA.multicontainer)

        PA.selected_cores.recalculate()  # make sure they make sense
        # repopulate the data to make sure it's correct on the screen
        self.total_cores_field.set_value(str(self.num_cores))
        self.total_drives_field.set_value(str(self.num_drives))
        self.num_hosts_field.set_value(str(len(PA.selected_hosts)))
        self.usable_cores_field.set_value(str(PA.selected_cores.usable))
        self.fe_cores_field.set_value(str(PA.selected_cores.fe))
        self.compute_cores_field.set_value(str(PA.selected_cores.compute))
        self.drives_cores_field.set_value(str(PA.selected_cores.drives))

        self.name_field.set_value(PA.clustername)
        if PA.datadrives is None or (PA.datadrives + PA.paritydrives) > len(PA.selected_hosts):
            PA.datadrives = len(PA.selected_hosts) - 2
            PA.paritydrives = 2

        if PA.datadrives > 16:
            PA.datadrives = 16

        self.data_field.set_value(str(PA.datadrives))
        self.parity_field.set_value(str(PA.paritydrives))
        self.spares_field.set_value(str(PA.hot_spares))
        self.misc_field.set_value(PA.misc)

    # save the values that are on the screen so we can repopulate it later
    def save_values(self):
        PA = self.parentApp
        PA.selected_cores.usable = int(self.usable_cores_field.value)
        PA.selected_cores.fe = int(self.fe_cores_field.value)
        PA.selected_cores.compute = int(self.compute_cores_field.value)
        PA.selected_cores.drives = int(self.drives_cores_field.value)
        PA.clustername = self.name_field.value
        PA.datadrives = int(self.data_field.value)
        PA.paritydrives = int(self.parity_field.value)
        PA.hot_spares = int(self.spares_field.value)
        PA.misc = self.misc_field.value
        PA.dedicated = True if 0 in self.misc_field.value else False
        PA.auto_failure_domain = True if 1 in self.misc_field.value else False
        PA.cloud_enable = True if 2 in self.misc_field.value else False

    # this happens when they hit the OK button
    def on_ok(self):
        # The next two lines terminate the app cleanly, so we should generate the config
        self.save_values()
        self.parentApp.setNextForm(None)
        self.parentApp.cleanexit = True

    # this happens when they hit the Cancel/Previous button
    def on_cancel(self):
        self.save_values()
        self.parentApp.switchFormPrevious()  # go to previous screen; they hit 'Prev'

    def analyse_cores(self):
        # let's gather together the info
        xref_dict = dict()
        xref_dict["cores"] = dict()
        xref_dict["threads"] = dict()

        for hostname in self.parentApp.selected_hosts:
            xref_dict["cores"][hostname] = self.parentApp.target_hosts.usable_hosts[hostname].num_cores
            xref_dict["threads"][hostname] = self.parentApp.target_hosts.usable_hosts[hostname].threads_per_core

        # are they all the same?
        reference_cores = 0
        ref_threads_per_core = 0
        errors = False
        for host, cores in xref_dict["cores"].items():
            if reference_cores == 0:
                reference_cores = cores
                #continue
            else:
                if cores != reference_cores:
                    # Error!   hosts have different number of cores!
                    errors = True
                    #break

            if ref_threads_per_core == 0:
                ref_threads_per_core = xref_dict["threads"][host] # should be for reference_host
                #continue
            else:
                if xref_dict["threads"][host] != ref_threads_per_core:
                    # Error!   hosts have different number of cores!
                    errors = True
                #    break

        if errors:
            # make noise
            wekatui.notify_confirm("The hosts are not homogenous; they have different numbers of cores/threads.",
                                   title="Error", form_color='STANDOUT', wrap=True, editw=1)

        return int(reference_cores / ref_threads_per_core)

    def analyse_drives(self):
        # let's gather together the info
        num_drives = dict()
        for hostname in self.parentApp.selected_hosts:
            num_drives[hostname] = len(self.parentApp.target_hosts.usable_hosts[hostname].drives)

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
        # if errors:
        # make noise
        # wekatui.notify_confirm("The hosts are not homogenous; they have different numbers of drives.",
        #                         title="Error", form_color='STANDOUT', wrap=True, editw=1)

        return reference_drives


# the form for selecting what hosts will be in the cluster
class SelectHostsForm(CancelNextForm):
    def __init__(self, *args, **kwargs):
        self.help = """Select the hosts that will be in your cluster.\n\n"""
        self.help = self.help + movement_help
        super(SelectHostsForm, self).__init__(*args, help=self.help, **kwargs)

    def create(self):
        self.sorted_hosts = list()
        self.possible_dps = self.guess_networks(self.parentApp.target_hosts)
        # what happens when there's only 1 possible dp network?
        self.dataplane_networks_field = self.add(Networks, fieldname="networks",
                                                 scroll_exit=True,  # allow them to exit using arrow keys
                                                 max_height=5,  # not too big - need room below for next field
                                                 use_two_lines=True,  # input fields start on 2nd line
                                                 rely=2,  # put it high on the screen
                                                 max_width=72,
                                                 begin_entry_at=2,  # make the list under the title
                                                 name='Select DP Networks:',  # label/title
                                                 # values=["255.255.255.255/32 - 200 Gbps"]) # testing
                                                 values=self.possible_dps)

        self.num_hosts_field = self.add(wekatui.TitleFixedText, fieldname="num_hosts", name="Number of Hosts:",
                                        labelColor='NO_EDIT',
                                        rely=8, relx=2,
                                        use_two_lines=False, editable=False, max_width=22)
        self.hosts_field = self.add(Hosts, fieldname="hosts",
                                    scroll_exit=True,  # allow them to exit using arrow keys
                                    use_two_lines=True,  # input fields start on 2nd line
                                    # rely=2,  # put it high on the screen
                                    # relx=39,  # place to the right of Networks (above)
                                    relx=2, rely=10,
                                    max_width=40,
                                    begin_entry_at=2,  # make the list under the title
                                    name='Select Hosts:')
        # values=["01234567890123456789012345678901234567890123456789", # testing
        #        "          1         2         3         4"] ) # testing
        self.ha_field = self.add(HighAvailability, name="High Availability:",
                                 scroll_exit=True,  # allow them to exit using arrow keys
                                 rely=10, relx=41,
                                 use_two_lines=True, editable=True,
                                 begin_entry_at=2,  # make the list under the title
                                 values=["Yes", "No"])
        #self.multicontainer_field = self.add(multicontainer, name="multicontainer Configuration:",
        #                          scroll_exit=True,  # allow them to exit using arrow keys
        #                          rely=14, relx=41,
        #                          use_two_lines=True, editable=True,
        #                          begin_entry_at=2,  # make the list under the title
        #                          values=["Yes", "No"])

    def beforeEditing(self):
        PA = self.parentApp
        if hasattr(self, "multicontainer_field"):
            if PA.multicontainer:
                self.multicontainer_field.set_value([0])  # set default value to Yes.
            else:
                self.multicontainer_field.set_value([1])  # set default value to No.

    def on_ok(self):
        PA = self.parentApp
        # PA.selected_hosts = dict()  # toss any old values
        # if len(self.hosts_field.value) < 5:
        #    # they didn't select any
        #    wekatui.notify_wait("You must select at least 5 hosts", title='ERROR')
        #    return
        # for index in self.hosts_field.value:  # an index into the orig list, ie: [0,2,4,6,7]
        #    PA.selected_hosts[PA.sorted_hosts[index]] = PA.target_hosts.usable_hosts[PA.sorted_hosts[index]]

        # find the amount of RAM we can use...  min of all hosts in the cluster
        for host in PA.selected_hosts.values():
            try:
                if int(host.total_ramGB) < self.min_host_ramGB:
                    PA.min_host_ramGB = int(host.total_ramGB)
            except AttributeError:  # haven't set self.min_host_ramGB yet...
                PA.min_host_ramGB = int(host.total_ramGB)

        if self.ha_field.value == [0]:
            PA.HighAvailability = True
        else:
            PA.HighAvailability = False

        if hasattr(self, "multicontainer_field") and self.multicontainer_field.value == [0]:
            PA.multicontainer = True
        else:
            PA.multicontainer = False

        PA.setNextForm("SelectCoresForm")

    def on_cancel(self):
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
        for iface, nic in sorted(hostlist.referencehost_obj.nics.items()):
            output.append(f"{iface}: {nic.with_prefixlen} - {nic.type}, {int(nic.speed / 1000)} Gbps, " +
                          f"{len(hostlist.accessible_hosts[iface])} hosts")
            self.nets.append(iface)

        return output
