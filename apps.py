################################################################################################
# Apps
################################################################################################
import curses
import sys
from logging import getLogger

from weka import shutdown_curses

log = getLogger(__name__)

import wekatui
from forms import SelectHostsForm, SelectCoresForm


class WekaTheme(wekatui.ThemeManager):
    default_colors = {
        'DEFAULT': 'WHITE_BLACK',
        'FORMDEFAULT': 'WHITE_BLACK',
        'NO_EDIT': 'YELLOW_BLACK',
        'STANDOUT': 'CYAN_BLACK',
        'CURSOR': 'WHITE_BLACK',
        'CURSOR_INVERSE': 'BLACK_WHITE',
        'LABEL': 'GREEN_BLACK',
        'LABELBOLD': 'GREEN_BLACK',
        'CONTROL': 'YELLOW_BLACK',
        'WARNING': 'RED_BLACK',
        'CRITICAL': 'BLACK_RED',
        'GOOD': 'GREEN_BLACK',
        'GOODHL': 'GREEN_BLACK',
        'VERYGOOD': 'BLACK_GREEN',
        'CAUTION': 'YELLOW_BLACK',
        'CAUTIONHL': 'BLACK_YELLOW',
        'BOLD': 'WHITE_BLACK',  # basically, no bold
    }


#
# the base app - this is the entrypoint to the UI
#
class WekaConfigApp(wekatui.NPSAppManaged):
    STARTING_FORM = "SelectHostsForm"  # the first form to display

    def __init__(self, hostgroup):
        self.target_hosts = hostgroup  # WekaHostGroup object
        self.selected_dps = list()
        self.selected_hosts = dict()
        self.selected_cores = None
        self.clustername = None
        self.datadrives = None
        self.paritydrives = None
        self.cleanexit = False
        self.hot_spares = 1
        self.misc = [0, 1, 2]
        self.dedicated = None
        self.auto_failure_domain = None
        self.cloud_enable = None
        self.weka_ver = hostgroup.referencehost_obj.version.split('.')
        if int(self.weka_ver[0]) < 4:
            self.Multicontainer = False
        else:
            self.Multicontainer = True
        self.protocols_memory = None

        log.info("starting UI...")

        super(WekaConfigApp, self).__init__()

    def onStart(self):
        wekatui.setTheme(WekaTheme)
        #try:
        self.addForm("SelectHostsForm", SelectHostsForm, "Weka Configurator (Hosts)")
        self.addForm("SelectCoresForm", SelectCoresForm, "Weka Configurator (Cores)")
        #except wekatui.wgwidget.NotEnoughSpaceForWidget:
        #    shutdown_curses(None)
        #    log.error("Your window is too small to display the screen.  Please make it bigger.")
        #    sys.exit(1)
        #except Exception as exc:
        #    shutdown_curses(None)
        #    log.error(f"Unknown UI Error {exc}")
        #    sys.exit(1)

    # on exit of application - when next form is None
    def onCleanExit(self):
        pass  # We might want to do something here; perhaps move the output task here?
