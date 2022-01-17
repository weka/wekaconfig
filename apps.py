################################################################################################
# Apps
################################################################################################

import npyscreen
from forms import SelectHostsForm, SelectCoresForm

class WekaTheme(npyscreen.ThemeManager):

    default_colors = {
        'DEFAULT'     : 'WHITE_BLACK',
        'FORMDEFAULT' : 'WHITE_BLACK',
        'NO_EDIT'     : 'YELLOW_BLACK',
        'STANDOUT'    : 'CYAN_BLACK',
        'CURSOR'      : 'WHITE_BLACK',
        'CURSOR_INVERSE': 'BLACK_WHITE',
        'LABEL'       : 'GREEN_BLACK',
        'LABELBOLD'   : 'GREEN_BLACK',
        'CONTROL'     : 'YELLOW_BLACK',
        'WARNING'     : 'RED_BLACK',
        'CRITICAL'    : 'BLACK_RED',
        'GOOD'        : 'GREEN_BLACK',
        'GOODHL'      : 'GREEN_BLACK',
        'VERYGOOD'    : 'BLACK_GREEN',
        'CAUTION'     : 'YELLOW_BLACK',
        'CAUTIONHL'   : 'BLACK_YELLOW',
        'BOLD': 'WHITE_BLACK', # basically, no bold
    }

class WekaConfigApp(npyscreen.NPSAppManaged):
    STARTING_FORM = "SelectHostsForm"

    def __init__(self, hostlist):
        self.target_hosts = hostlist  # STEMHost objects
        self.selected_dps = list()
        self.selected_hosts = dict()
        self.selected_cores = None
        self.clustername = None
        self.datadrives = None
        self.paritydrives = None
        self.cleanexit = False
        self.misc = None
        self.dedicated = None
        self.auto_failure_domain = None
        self.cloud_enable = None

        super(WekaConfigApp, self).__init__()

    def onStart(self):
        npyscreen.setTheme(WekaTheme)
        self.addForm("SelectHostsForm", SelectHostsForm, "Weka Configurator (Hosts)")
        #self.addForm("Hosts", SelectHosts, "Weka Configurator (Hosts)")
        self.addForm("SelectCoresForm", SelectCoresForm, "Weka Configurator (Cores)")
        fred = 1

    # on exit of application - when next form is None
    # def onCleanExit(self):
    #    print(f"selected dp networks are: {self.selected_dps}")
