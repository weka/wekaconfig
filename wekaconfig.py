################################################################################################
# Main
################################################################################################
import argparse
import logging
import os
import sys

from wekapyutils.wekalogging import configure_logging, register_module, DEFAULT

from apps import WekaConfigApp
from output import WekaCluster
from weka import scan_hosts

# get root logger
log = logging.getLogger()

if __name__ == '__main__':
    progname = sys.argv[0]
    parser = argparse.ArgumentParser(description="Weka Cluster Configurator")
    parser.add_argument("hosts", type=str, nargs="*",
                        help="a list of hosts to configure, or none to use cluster beacons", default=None)
    parser.add_argument("-p", "--port", type=int, default=14000, nargs="?",help="base TCP port to connect to")
    parser.add_argument("-v", "--verbosity", action="count", default=0, help="increase output verbosity")
    parser.add_argument("--skip-gateway-check", dest="gateway_check", default=False, action="store_true",
                        help="skip checking for gateways")
    parser.add_argument("--version", dest="version", default=False, action="store_true",
                        help="Display version number")
    args = parser.parse_args()

    if args.version:
        print(f"{progname} version 2025.02.13")
        sys.exit(0)

    if args.verbosity == 0:
        loglevel = logging.INFO
    elif args.verbosity == 1:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.DEBUG

    # set up logging
    console_handler = logging.StreamHandler()
    console_handler.setLevel(loglevel)
    console_handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
    log.addHandler(console_handler)

    # add a new logging handler to capture all output to a file
    logfile_handler = logging.FileHandler("wekaconfig.log")
    logfile_handler.setLevel(logging.DEBUG)
    logfile_handler.setFormatter(logging.Formatter(
        "%(asctime)s:%(filename)s:%(lineno)s:%(funcName)s():%(levelname)s:%(message)s"))
    log.addHandler(logfile_handler)

    # set the logging level for the root logger - this will be the default for all submodules
    log.setLevel(logging.DEBUG)

    # set submodule logging levels - let them be quiet
    logging.getLogger("paramiko").setLevel(logging.ERROR)
    logging.getLogger("wekalib").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("wekapyutils.sthreads").setLevel(logging.ERROR)
    logging.getLogger("wekapyutils.wekassh").setLevel(logging.ERROR)
    #logging.getLogger("wekassh").setLevel(logging.ERROR)

    # quiet down fabric and invoke - they're really chatty
    logging.getLogger("fabric").setLevel(logging.ERROR)
    logging.getLogger("invoke").setLevel(logging.ERROR)

    # add a new logging handler so we can log summary messages to a file, but not to the console
    summary_log = logging.getLogger("summary")
    summary_log.addHandler(logfile_handler)
    summary_log.propagate = False

    try:
        wd = sys._MEIPASS  # for PyInstaller - this is the temp dir where we are unpacked
    except AttributeError:
        wd = os.path.dirname(progname)

    # hack for broken definition of xterm-256color
    os.environ["TERM"] = "xterm-256color"
    os.environ["TERMINFO"] = f"{wd}/terminfo"  # we carry our own definition
    print(f"Setting TERMINFO to {os.environ['TERMINFO']}")

    print(f"collecting host data... please wait...")
    log.info("*******************  Starting Weka Configurator  *******************")
    host_list = scan_hosts(args.hosts, args.port, args.gateway_check)

    # pause here so the user can review what's happened before we go to full-screen mode
    if len(host_list.reference_host.nics) < 1:
        log.critical(f"There are no usable networks, aborting.")
        sys.exit(1)
    print(f"Scanning Complete.  Press Enter to continue: ", end='')
    user = input()

    # UI starts here - it consists of an App, which has Forms (pages).  Each Form has data entry/display Widgets.
    config = WekaConfigApp(host_list)
    config.run()
    if not config.cleanexit:
        print("App was cancelled.")
    else:
        print(f"App exited - writing config.sh")

        cluster = WekaCluster(config)
        fo = open("config.sh", "w")
        cluster.cluster_config(fo)
        os.chmod("config.sh", 0o755)
