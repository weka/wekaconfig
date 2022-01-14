################################################################################################
# Apps
################################################################################################

import npyscreen
from forms import SelectDPNetworks, SelectCores

class WekaTheme(npyscreen.ThemeManager):

    default_colors = {
        'DEFAULT'     : 'WHITE_BLACK',
        'FORMDEFAULT' : 'WHITE_BLACK',
        'NO_EDIT'     : 'YELLOW_BLACK',
        'STANDOUT'    : 'CYAN_BLACK',
        'CURSOR'      : 'CYAN_BLACK',
        'CURSOR_INVERSE': 'BLACK_CYAN',
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
    }

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
        npyscreen.setTheme(WekaTheme)
        self.addForm("SelectNetworks", SelectDPNetworks, "Weka Configurator (Networks)")
        #self.addForm("Hosts", SelectHosts, "Weka Configurator (Hosts)")
        self.addForm("SelectCores", SelectCores, "Weka Configurator (Cores)")

    # on exit of application - when next form is None
    # def onCleanExit(self):
    #    print(f"selected dp networks are: {self.selected_dps}")
