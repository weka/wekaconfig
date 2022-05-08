################################################################################################
# Main
################################################################################################
import argparse
import logging
import os
import sys

from apps import WekaConfigApp
from output import WekaCluster
from weka import scan_hosts
from wekalogging import configure_logging

# get root logger
log = logging.getLogger()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Weka Cluster Configurator")
    parser.add_argument("host", type=str, nargs="?", help="a host to talk to", default="localhost")
    parser.add_argument("-v", "--verbosity", action="count", default=0, help="increase output verbosity")
    parser.add_argument("--version", dest="version", default=False, action="store_true",
                        help="Display version number")
    args = parser.parse_args()

    if args.version:
        print(f"{args.prog} version 1.0.1")
        sys.exit(0)

    configure_logging(log, args.verbosity)

    # hack for Ubuntu's broken definition of xterm-256color
    if os.environ["TERM"] == "xterm-256color" and not os.path.exists("/usr/share/terminfo/x/xterm-256color"):
        os.environ["TERMINFO"] = f"{os.getcwd()}/terminfo"   # we carry our own definition
        print(f"Setting TERMINFO to {os.environ['TERMINFO']}")

    if args.host == "localhost":
        import platform
        args.host = platform.node()
    print(f"target host is {args.host}")
    print(f"collecting host data... please wait...")
    host_list = scan_hosts(args.host)

    # pause here so the user can review what's happened before we go to full-screen mode
    print(f"Scanning Complete.  Press Enter to continue: ", end='')
    user = input()

    # UI starts here - it consists of an App, which has Forms (pages).  Each Form has data entry/display Widgets.
    config = WekaConfigApp(host_list)
    config.run()
    if not config.cleanexit:
        print("App was cancelled.")
    else:
        print(f"App exited - writing config.txt")
        # print(f"target hosts = {config.target_hosts}")
        # print(f"nets = {config.selected_dps}")
        # print(f"hosts = {config.selected_hosts}")
        # print(f"cores = {config.selected_cores}")
        # print(f"name = {config.clustername}")
        # print(f"datadrives = {config.datadrives}")
        # print(f"parity = {config.paritydrives}")

        cluster = WekaCluster(config)
        fo = open("config.txt", "w")
        cluster.cluster_config(fo)
