################################################################################################
# Widgets
################################################################################################

import curses.ascii

import npyscreen

movement_help = """Cursor movement:
    arrow keys: up, down, left, right - move between and within fields
    Space, Enter: select item
    Tab: move to next field
    """


class WekaTitleText(npyscreen.TitleText):
    """Label:text input field"""

    def __init__(self, *args, label='', entry_field_width=6, **keywords):
        label = label + ':'
        keywords["name"] = label
        keywords["use_two_lines"] = False
        self.entry_field_width = entry_field_width
        super(WekaTitleText, self).__init__(*args, **keywords)
        self.entry_widget.remove_complex_handler(self.entry_widget.t_input_isprint)
        self.entry_widget.add_complex_handlers([(self.t_input_length, self.h_toss_input)])
        self.entry_widget.add_complex_handlers([(self.entry_widget.t_input_isprint, self.entry_widget.h_addch)])
        fred = 2

    def t_input_length(self, inp):
        if len(self.value) >= self.entry_field_width:
            curses.beep()
            return True
        return False

    def h_toss_input(self, inp):
        return True


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
        self.parent.fe_cores.set_value(str(PA.selected_cores.fe))
        self.parent.compute_cores.set_value(str(PA.selected_cores.compute))
        self.parent.drives_cores.set_value(str(PA.selected_cores.drives))

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
