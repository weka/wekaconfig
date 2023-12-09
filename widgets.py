################################################################################################
# Widgets
################################################################################################

import curses.ascii

import wekatui

movement_help = """Cursor movement:
    arrow keys: up, down, left, right - move between and within fields
    Space, Enter: select item
    Tab: move to next field
    """


# base classes

# a data entry field - "label: entryfield" format.   Takes text with a fixed width
class WekaTitleText(wekatui.TitleText):
    """Label:text input field"""

    def __init__(self, *args, label='', entry_field_width=6, **keywords):
        label = label + ':'
        keywords["name"] = label
        keywords["use_two_lines"] = False
        self.entry_field_width = entry_field_width
        super(WekaTitleText, self).__init__(*args, **keywords)
        # each of these handlers determine if the input should be accepted.  The second function is only called if
        # the first returns True.
        self.entry_widget.remove_complex_handler(self.entry_widget.t_input_isprint)
        self.entry_widget.add_complex_handlers([(self.t_input_length, self.h_toss_input)])
        self.entry_widget.add_complex_handlers([(self.entry_widget.t_input_isprint, self.entry_widget.h_addch)])
        fred = 2

    # don't allow then to exceed the max field width
    def t_input_length(self, inp):
        if len(self.value) >= self.entry_field_width:
            curses.beep()
            return True
        return False

    # gobble up the input without saving it (used for error entries, like unknown/disallowed chars)
    def h_toss_input(self, inp):
        return True


# a data entry field - "label: entryfield" format.   Takes only numeric with a fixed width
class WekaTitleNumeric(wekatui.TitleText):
    """Label:numeric input field"""

    def __init__(self, *args, label='', entry_field_width=6, **keywords):
        label = label + ':'
        keywords["name"] = label
        keywords["use_two_lines"] = False
        self.entry_field_width = entry_field_width
        super(WekaTitleNumeric, self).__init__(*args, **keywords)
        self.entry_widget.add_complex_handlers([(self.t_input_length, self.h_toss_input)])
        self.entry_widget.add_complex_handlers([(self.t_input_isdigit, self.entry_widget.h_addch)])
        self.entry_widget.remove_complex_handler(self.entry_widget.t_input_isprint)

    def t_input_length(self, inp):
        if len(self.value) >= self.entry_field_width:
            curses.beep()
            return True
        return False

    def h_toss_input(self, inp):
        return True

    # only allows numbers to be input (ie: 0 to 9)
    def t_input_isdigit(self, inp):
        import curses
        if curses.ascii.isdigit(inp):
            return True
        else:
            curses.beep()
            return False


class WekaTitleFixedText(wekatui.TitleFixedText):
    """Label: value (non-input/no editing) field"""

    def __init__(self, *args, label='', entry_field_width=6, **keywords):
        label = label + ':'
        keywords["name"] = label
        keywords["labelColor"] = 'NO_EDIT'
        keywords["editable"] = False
        keywords["use_two_lines"] = False
        self.entry_field_width = entry_field_width
        super(WekaTitleFixedText, self).__init__(*args, **keywords)


class NameWidget(WekaTitleText):
    """Label: name (as in hostname, clustername, etc) field"""

    def __init__(self, *args, entry_field_width=6, **keywords):
        self.entry_field_width = entry_field_width
        keywords["entry_field_width"] = entry_field_width
        super(NameWidget, self).__init__(*args, **keywords)
        self.entry_widget.remove_complex_handler(self.entry_widget.t_input_isprint)
        self.entry_widget.add_complex_handlers([(self.t_input_isname, self.entry_widget.h_addch)])

    # only allows numbers to be input (ie: 0 to 9)
    def t_input_isname(self, inp):
        import curses

        if curses.ascii.isspace(inp):
            wekatui.notify_wait("Only a-z,A-Z,0-9,-, and _ are allowed in names")
            curses.beep()
            return False
        elif curses.ascii.isalnum(inp):
            return True
        elif inp == 0x5f or inp == 0x2d or inp == 0x2e:
            return True
        else:
            curses.beep()
            wekatui.notify_wait("Only a-z,A-Z,0-9,.,-, and _ are allowed in names")
            return False


class CoresWidgetBase(WekaTitleNumeric):
    """helper base class for weka cores input"""

    def __init__(self, *args, fieldname='', **keywords):
        self.fieldname = fieldname
        self.last_value = None
        super(CoresWidgetBase, self).__init__(*args, **keywords)

    def safe_to_exit(self):
        if len(self.value) == 0:
            wekatui.notify_wait("Please enter a number")
            return False

        self.intval = int(self.value)

        message = self.check_value()
        if message is not None:
            wekatui.notify_wait(message)
            return False

        self.set_values()
        self.display()
        return True

    def set_values(self):
        """update the parent"""
        PA = self.parent.parentApp
        #PA.selected_cores.recalculate()   # maybe not a good idea to do this only here... spread out logic?

        # to get all of the cores fields to display...
        # maybe we can cycle through the self.parent.* fields, and see
        # if they are in widget.__class__.__mro__?  ie:
        # for widget in self._widgets__:
        #     if CoresWidgetBase in widget.__class__.__mro__:
        #         widget.display()

        # update on-screen values from PA
        self.parent.fe_cores_field.set_value(str(PA.selected_cores.fe))
        self.parent.compute_cores_field.set_value(str(PA.selected_cores.compute))
        self.parent.drives_cores_field.set_value(str(PA.selected_cores.drives))

        PA.selected_cores.used = PA.selected_cores.fe + PA.selected_cores.compute + PA.selected_cores.drives
        self.parent.used_cores_field.set_value(str(PA.selected_cores.used))
        self.parent.used_cores_field.display()
        self.parent.weka_cores_field.set_value(str(PA.selected_cores.usable))
        self.parent.os_cores_field.set_value(str(PA.selected_cores.res_os))
        self.parent.proto_cores_field.set_value(str(PA.selected_cores.res_proto))
        self.display()


    def check_value(self):
        # override me
        pass


class UsableCoresWidget(CoresWidgetBase):
    """specifically for total usable cores"""

    # changed to read-only display field... so this should be unused
    def check_value(self):
        PA = self.parent.parentApp

        if PA.Multicontainer:
            maxcores = PA.selected_cores.total - 2
        else:
            if PA.selected_cores.total < 22:
                maxcores = PA.selected_cores.total - 2
            else:
                maxcores = 19  # max 19 per container and this is SBC

        if self.intval not in range(1, maxcores + 1):
            return f"Please enter a number between 1 and {maxcores}"
        PA.selected_cores.usable = self.intval
        return None


class FeCoresWidget(CoresWidgetBase):
    """specific for FrontEnd cores"""

    # check_value will not allow them to leave the field if we return not None
    def check_value(self):
        PA = self.parent.parentApp
        if self.intval > PA.selected_cores.usable - 2:  # have to leave 1 compute and 1 drives core!
            return "You must allow for at least 1 of each core type"
        elif self.intval <= 0:
            return "You must have at least 1 FE core"
        self.parent.parentApp.selected_cores.fe = self.intval
        return None


class DrivesCoresWidget(CoresWidgetBase):
    """specific for Drives cores"""

    # check_value will not allow them to leave the field if we return not None
    def check_value(self):
        PA = self.parent.parentApp

        if self.intval > PA.selected_cores.usable - 2:  # have to leave 1 compute and 1 drives core!
            return "You must allow for at least 1 of each core type"
        elif self.intval <= 0:
            return "You must have at least 1 DRIVES core"

        self.parent.parentApp.selected_cores.drives = self.intval
        return None


class ComputeCoresWidget(CoresWidgetBase):
    """specific for Compute cores"""

    def check_value(self):
        PA = self.parent.parentApp

        if self.intval > PA.selected_cores.usable - 2:  # have to leave 1 compute and 1 drives core!
            return "You must allow for at least 1 of each core type"
        elif self.intval <= 0:
            return "You must have at least 1 COMPUTE core"

        if self.intval + PA.selected_cores.fe + PA.selected_cores.drives > PA.selected_cores.usable:
            return "Too many total cores - please re-adjust"

        self.parent.parentApp.selected_cores.compute = self.intval
        return None


class DataParityBase(CoresWidgetBase):
    """helper for data/parity drives input"""

    def check_value(self):
        PA = self.parent.parentApp
        self.clustersize = len(PA.selected_hosts)
        if self.intval > self.clustersize - 2:
            return f"The most data drives for a cluster of {self.clustersize} hosts is {self.clustersize - 2}"
        elif self.intval + PA.paritydrives > self.clustersize:
            PA.paritydrives = 2

        if self.intval + PA.paritydrives == self.clustersize \
                and self.clustersize > 5:
            wekatui.notify_wait(f"Stripe width" \
                                + f" ({self.intval}+{PA.paritydrives}) matches cluster "
                                + "size, forming a narrow cluster. Using a stripe width "
                                + f"of {self.intval - 1}+{PA.paritydrives} is strongly "
                                + "recommended instead.")
        return self._check_value()

    def _check_value(self):
        # override me
        pass


class DataWidget(DataParityBase):
    """specific for data drives input"""

    def _check_value(self):
        PA = self.parent.parentApp
        max_data = (self.clustersize - PA.paritydrives) if self.clustersize < (16 + PA.paritydrives) else 16
        if self.intval not in range(3, max_data + 1):
            return f"Data drives must be between 3 and {max_data}"
        return None

    def set_values(self):
        PA = self.parent.parentApp
        PA.datadrives = self.intval


class ParityWidget(DataParityBase):
    """specific for parity drives input"""

    def _check_value(self):
        if self.intval == 4 and self.clustersize <= 8:
            return "Parity of 4 can only be used with clusters with more than 8 hosts"
        if self.intval not in [2, 4]:
            return "Parity must be either 2 or 4"
        return None

    def set_values(self):
        PA = self.parent.parentApp
        PA.paritydrives = self.intval


class SparesWidget(DataParityBase):
    """specific for data drives input"""

    def _check_value(self):
        #PA = self.parent.parentApp
        #stripe_width = PA.datadrives + PA.paritydrives
        #max_spares = self.clustersize - stripe_width
        #if self.intval > max_spares:
        #    return f"Hot Spares must be between 0 and {max_spares}"
        if self.intval >= self.clustersize or self.intval < 0:
            return f"Hot Spares out of range"
        return None

    def set_values(self):
        PA = self.parent.parentApp
        PA.hot_spares = self.intval


class MemoryWidget(CoresWidgetBase):
    """specific for parity drives input"""

    def __init__(self, *args, label='', entry_field_width=4, relx=0, rely=0, **keywords):
        begin_entry_at = len(label) + 2  # leave room for ": "
        self.editable = True
        super(MemoryWidget, self).__init__(*args, label=label, begin_entry_at=begin_entry_at,
                                           entry_field_width=entry_field_width, relx=relx, rely=rely, **keywords)

    def check_value(self):
        PA = self.parent.parentApp
        #usable_ram = self.default_value()
        #if self.intval < 50:
        #    return f'{self.intval}GB, really?  How do you expect to run Weka on {self.intval}GB? Please enter a value between 50GB and {usable_ram}GB'
        if self.intval > PA.min_host_ramGB:
            return f'{self.intval}GB of ram is greater than the max usable of {PA.min_host_ramGB}GB'
        PA.protocols_memory = str(self.intval)
        return None

    #def default_value(self):
    #    PA = self.parent.parentApp
    #    if not hasattr(PA, "protocols_memory"):
    #        PA.protocols_memory = 0
    #    return PA.protocols_memory

    def set_values(self):
        PA = self.parent.parentApp
        #PA.protocols_memory = self.intval
        self.set_value(str(PA.protocols_memory))
        self.display()


class OptionsWidget(wekatui.TitleMultiSelect):
    def when_value_edited(self):
        # if 0 is in value, Enable HA == True
        # if 1 is in value, MCB == True
        parent = self.parent
        PA = parent.parentApp

        # possible values:
        # [0,1] = HA, MCB
        # [0] = HA
        # [1] = MCB
        # [] = neither

        edited_value = False

        if 0 in self.value:     # user selected HA True
            if len(PA.selected_dps) == 1 and not PA.one_net_multi_nic:
                # beep and ignore
                curses.beep()
                self.value.remove(0)
                PA.HighAvailability = False
                edited_value = True
            else:
                PA.HighAvailability = True
        else:
            PA.HighAvailability = False

        if 1 in self.value:
            if int(PA.weka_ver[0]) < 4:
                # beep and ignore
                curses.beep()
                self.value.remove(1)
                PA.Multicontainer = False
                edited_value = True
            else:
                PA.Multicontainer = True
        else:
            PA.Multicontainer = False

        self.display()
        return edited_value

    def safe_to_exit(self):
        if self.when_value_edited():
            return False
        else:
            return True

class BiasWidget(wekatui.TitleMultiSelect):
    def when_value_edited(self):
        # if 0 is in value, Enable Protocols == True
        # if 1 is in value, Protocols are Primary == True
        # if 2 is in value, Drives Bias == True
        # anything not in value == False for that item

        # if they set protocols are primary, ensure Protocols is set
        if 1 in self.value and 0 not in self.value:
            self.value.insert(0, 0)  # turn on Protocols if they select Primary

        self.set_values()
        self.display()

    # make darn sure they set it properly
    def safe_to_exit(self):
        # when_value_editied() isn't always called...
        if 1 in self.value and 0 not in self.value:
            self.value.insert(0, 0)  # turn on Protocols if they select Primary
            self.set_values()
            self.display()
            return False
        else:
            # set bias settings in parent? Or just reference the field from the other objects?
            self.set_values()
            self.display()
            return True

    def set_values(self, **kwargs):
        PA = self.parent.parentApp
        PA.selected_cores.protocols = True if 0 in self.value else False
        PA.selected_cores.proto_primary = True if 1 in self.value else False
        PA.selected_cores.drives_bias = True if 2 in self.value else False

        # auto-calc on field exit
        self.parent.parentApp.selected_cores.drives = self.parent.parentApp.selected_cores.num_actual_drives
        self.parent.parentApp.selected_cores.calculate()

        if PA.selected_cores.protocols:
            if not PA.selected_cores.proto_primary:
                PA.protocols_memory = 20     # reserve RAM for protocol
            else:
                PA.protocols_memory = 60     # reserve RAM for protocol
        else:
            PA.protocols_memory = 0

        # cause core re-calc and re-display of all fields
        self.parent.fe_cores_field.set_values() # part of the base class, so any one will do all
        self.parent.drives_cores_field.set_values() # part of the base class, so any one will do all
        self.parent.compute_cores_field.set_values() # part of the base class, so any one will do all
        self.parent.memory_field.set_values()

        self.parent.os_cores_field.display()
        self.parent.proto_cores_field.display()
        self.parent.weka_cores_field.display()
        self.parent.used_cores_field.display()

# a widget for displaying how many hosts there are (read-only)
class Hosts(wekatui.TitleMultiSelect):
    def when_value_edited(self):
        parent = self.parent
        # update the "Number of hosts" field on the lower-left
        parent.num_hosts_field.set_value(' ' + str(len(self.value)))
        parent.num_hosts_field.display()

        # exiting after selecting the hosts...
        # now might be a good time to determine if we have mixed networking, HA, or non-HA...
        PA = self.parent.parentApp
        PA.selected_hosts = dict()  # toss any old values
        for index in self.value:  # an index into the orig list, ie: [0,2,4,6,7]
            PA.selected_hosts[PA.sorted_hosts[index]] = PA.target_hosts.usable_hosts[PA.sorted_hosts[index]]

        # if len(PA.selected_dps) > 1:
        #    # then we've got either mixed networking or HA or both
        #    for dpname in PA.selected_dps:
        #        # if mixed networking, there should be both IB and ETH interfaces on the referencehost
        #        # if possibly HA, the interfaces should be... what? on same net?  nah. ask user?
        #        if dpname in PA.target_hosts.referencehost_obj.nics:
        #            pass
        # else:
        #    PA.HA = False

    def safe_to_exit(self):
        parent = self.parent
        PA = parent.parentApp
        if len(self.value) < 5:
            # they didn't select any
            wekatui.notify_wait("You must select at least 5 hosts", title='ERROR')
            return False

        # set up the Options field with default values
        parent.options_field.editable = True
        if len(PA.selected_dps) > 1 or PA.one_net_multi_nic or PA.HighAvailability:
            if 0 not in parent.options_field.value:
                parent.options_field.value.insert(0, 0)  # turn on HA
            PA.HighAvailability = True
        else:
            if 0 in parent.options_field.value:
                parent.options_field.remove(0)  # turn off HA
                PA.HighAvailability = False
        if PA.Multicontainer:
            if 1 not in parent.options_field.value:
                parent.options_field.value.insert(1, 1)  # turn on MCB
            PA.Multicontainer = True
        else:
            if 1 in parent.options_field.value:
                parent.options_field.value.remove(1)  # turn off MCB
                PA.Multicontainer = False
        parent.options_field.display()
        return True


#class HighAvailability(wekatui.TitleSelectOne):
#    _contained_widgets = wekatui.CheckBox
#
#    def __init__(self, *args, **keywords):
#        super().__init__(*args, **keywords)
#
#
#class Multicontainer(wekatui.TitleSelectOne):
#    _contained_widgets = wekatui.CheckBox
#
#    def __init__(self, *args, **keywords):
#        super().__init__(*args, **keywords)
#
#
#class YesNoCheckBox(wekatui.TitleSelectOne):
#    _contained_widgets = wekatui.CheckBox
#
#    def __init__(self, *args, **keywords):
#        super().__init__(*args, **keywords)


# a widget for selecting what the dataplane networks are
class Networks(wekatui.TitleMultiSelect):
    def when_value_edited(self):
        PA = self.parent.parentApp
        PA.selected_dps = list()  # clear the list
        PA.possible_hosts = set()
        for index in self.parent.dataplane_networks_field.value:
            # save the IPv4Network objects corresponding to the selected items
            #  find hosts on this network...
            for iface, nic in PA.target_hosts.referencehost_obj.nics.items():
                if nic.network == PA.nets[index]:   # is this nic on that network?
                    PA.possible_hosts |= PA.target_hosts.accessible_hosts[nic.name]
                    #for host in PA.target_hosts.accessible_hosts[nic.name]:
                    #    for nic in host.nics:
                    #        if nic.network == network:
                    #            PA.possible_hosts |= host.hostname
                    #            break

            #PA.possible_hosts |= PA.target_hosts.accessible_hosts[PA.nets[index]]
            PA.selected_dps.append(PA.nets[index])  # ie: "ib0" ?network number?

        PA.sorted_hosts = sorted(list(PA.possible_hosts))  # sorted hostnames
        PA.hosts_value = list(range(0, len(PA.sorted_hosts)))  # show all of them pre-selected
        if hasattr(self.parent, "hosts_field"):
            self.parent.hosts_field.set_value(PA.hosts_value)
            self.parent.hosts_field.set_values(sorted(PA.sorted_hosts))
            self.parent.hosts_field.when_value_edited()
        self.parent.display()

    # is it ok to leave the field when they try to exit?   Make sure they select something
    def safe_to_exit(self):
        # make sure they selected at least one dataplane network
        if len(self.parent.parentApp.selected_dps) == 0:
            return False
        return True
