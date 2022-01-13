################################################################################################
# Apps
################################################################################################

import npyscreen
from forms import SelectDPNetworks, SelectCores


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
        #self.addForm("Hosts", SelectHosts, "Weka Configurator (Hosts)")
        self.addForm("SelectCores", SelectCores, "Weka Configurator (Cores)")

    # on exit of application - when next form is None
    # def onCleanExit(self):
    #    print(f"selected dp networks are: {self.selected_dps}")
