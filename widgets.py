################################################################################################
# Widgets
################################################################################################

import curses.ascii

import npyscreen

import logic

movement_help = """Cursor movement:
    arrow keys: up, down, left, right - move between and within fields
    Space, Enter: select item
    Tab: move to next field
    """


# base classes

# a data entry field - "label: entryfield" format.   Takes text with a fixed width
class WekaTitleText(npyscreen.TitleText):
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
class WekaTitleNumeric(npyscreen.TitleText):
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


class WekaTitleFixedText(npyscreen.TitleFixedText):
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
            npyscreen.notify_wait("Only a-z,A-Z,0-9,-, and _ are allowed in names")
            curses.beep()
            return False
        elif curses.ascii.isalnum(inp):
            return True
        elif inp == 0x5f or inp == 0x2d or inp == 0x2e:
            return True
        else:
            curses.beep()
            npyscreen.notify_wait("Only a-z,A-Z,0-9,.,-, and _ are allowed in names")
            return False


class CoresWidgetBase(WekaTitleNumeric):
    """helper base class for weka cores input"""

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
        """update the parent"""
        PA = self.parent.parentApp
        PA.selected_cores.recalculate()
        self.parent.fe_cores_field.set_value(str(PA.selected_cores.fe))
        self.parent.compute_cores_field.set_value(str(PA.selected_cores.compute))
        self.parent.drives_cores_field.set_value(str(PA.selected_cores.drives))

    def check_value(self):
        # override me
        pass


class UsableCoresWidget(CoresWidgetBase):
    """specifically for total usable cores"""

    def check_value(self):
        if self.intval not in range(1, 20):
            return "Please enter a number between 1 and 19"
        self.parent.parentApp.selected_cores.usable = self.intval
        return None


class FeCoresWidget(CoresWidgetBase):
    """specific for FrontEnd cores"""

    def check_value(self):
        PA = self.parent.parentApp
        if self.intval > PA.selected_cores.usable:
            return "Cannot exceed Usable Cores"
        elif self.intval == 0:
            return "It is recommended to use at least 1 FE core"
        self.parent.parentApp.selected_cores.fe = self.intval
        return None


class DrivesCoresWidget(CoresWidgetBase):
    """specific for Drives cores"""

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
    """specific for Compute cores"""

    def check_value(self):
        PA = self.parent.parentApp

        if self.intval > PA.selected_cores.usable:
            return "Cannot exceed Usable Cores"
        elif self.intval == 0:
            npyscreen.notify_wait("It is recommended to use at least 1 Compute core")
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
        return self._check_value()

    def _check_value(self):
        # override me
        pass


class DataWidget(DataParityBase):
    """specific for data drives input"""

    def _check_value(self):
        if self.intval not in range(3, self.clustersize - 1):
            return f"Data drives must be between 3 and {self.clustersize - 2}"
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


class MemoryWidget(CoresWidgetBase):
    """specific for parity drives input"""
    def __init__(self, *args, label='', entry_field_width=4, relx=0, rely=0, **keywords):
        begin_entry_at=len(label) +2    # leave room for ": "
        self.editable = False   # default to not editable
        super(MemoryWidget, self).__init__(*args, label=label, begin_entry_at=begin_entry_at,
                                           entry_field_width=entry_field_width, relx=relx, rely=rely, **keywords)

    def check_value(self):
        usable_ram = self.parent.parentApp.min_host_ramGB - 20
        if self.intval < 50:
            return f'{self.intval}GB, really?  How do you expect to run Weka on {self.intval}GB? Please enter a value between 50GB and {usable_ram}GB'
        if self.intval > usable_ram:
            return f'{self.intval}GB of ram is greater than the max usable of {usable_ram}GB'
        return None

    def set_values(self):
        PA = self.parent.parentApp
        PA.memory = self.intval

class MiscWidget(npyscreen.TitleMultiSelect):
    def when_value_edited(self):
        parent = self.parent
        if 0 not in self.value:
            parent.memory_field.editable = True
        else:
            parent.memory_field.editable = False
            parent.memory_field.value = None
            parent.memory_field.display()



# a widget for displaying how many hosts there are (read-only)
class Hosts(npyscreen.TitleMultiSelect):
    def when_value_edited(self):
        parent = self.parent
        # update the "Number of hosts" field on the lower-left
        parent.num_hosts_field.set_value(' ' + str(len(parent.hosts_field.value)))
        parent.num_hosts_field.display()


# a widget for selecting what the dataplane networks are
class Networks(npyscreen.TitleMultiSelect):
    def when_value_edited(self):
        PA = self.parent.parentApp
        PA.selected_dps = list()  # clear the list
        for index in self.parent.dataplane_networks_field.value:
            # save the IPv4Network objects corresponding to the selected items
            PA.selected_dps.append(self.parent.nets[index])
        self.parent.analyze_networks()
        PA.possible_hosts, PA.excluded_hosts = logic.filter_hosts(PA.selected_dps, PA.target_hosts)
        PA.sorted_hosts = sorted(PA.possible_hosts.keys())  # list of names, not STEMHost objects
        PA.hosts_value = list(range(0, len(PA.sorted_hosts)))
        if hasattr(self.parent, "hosts_field"):
            self.parent.hosts_field.set_value(PA.hosts_value)
            self.parent.hosts_field.set_values(sorted(PA.sorted_hosts))
            self.parent.hosts_field.when_value_edited()
        #self.parent.num_hosts_field.set_value('  ' + str(len(PA.hosts_value)))
        self.parent.display()

    # is it ok to leave the field when they try to exit?   Make sure they select something
    def safe_to_exit(self):
        if len(self.parent.parentApp.selected_dps) == 0:
            return False
        return True
