
################################################################################################
# Main
################################################################################################
import argparse

from output import WekaCluster
from apps import WekaConfigApp
from weka import scan_hosts

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Weka Cluster Configurator")
    parser.add_argument("host", type=str, nargs="?", help="a host to talk to", default="localhost")
    parser.add_argument("-v", "--verbosity", action="count", default=0, help="increase output verbosity")
    parser.add_argument("--version", dest="version", default=False, action="store_true",
                        help="Display version number")
    args = parser.parse_args()

    print(f"target host is {args.host}")
    print(f"collecting host data... please wait...")
    host_list = scan_hosts(args.host)

    config = WekaConfigApp(host_list)
    config.run()
    if not config.cleanexit:
        print("App was cancelled.")
    else:
        print(f"App exited - writing config.txt")
        #print(f"target hosts = {config.target_hosts}")
        #print(f"nets = {config.selected_dps}")
        #print(f"hosts = {config.selected_hosts}")
        #print(f"cores = {config.selected_cores}")
        #print(f"name = {config.clustername}")
        #print(f"datadrives = {config.datadrives}")
        #print(f"parity = {config.paritydrives}")

        cluster = WekaCluster(config)
        fo = open("config.txt", "w")
        cluster.cluster_config(fo)