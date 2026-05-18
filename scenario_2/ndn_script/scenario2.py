import time
import random
import os
import csv

from minindn.minindn import Minindn
from minindn.apps.app_manager import AppManager
from minindn.apps.nfd import Nfd
from minindn.apps.nlsr import Nlsr
from mininet.log import setLogLevel, info
from minindn.util import MiniNDNCLI, getPopen

def run_trial(iteration, node_count, run_duration):
    Minindn.cleanUp()
    ndn = Minindn()
    ndn.start()
    
    info('Starting nfd and nlsr on nodes\n')
    AppManager(ndn, ndn.net.hosts, Nfd)
    AppManager(ndn, ndn.net.hosts, Nlsr)


    # Setup Producer and Poisoner
    numbers = random.sample(range(0, node_count-1), 2)
    poisoner = ndn.net[f'n{numbers[0]}']    
    producer = ndn.net[f'n{numbers[1]}']
    unmngd_nodes = [n for n in ndn.net.hosts if n.name not in [producer.name, poisoner.name]]
    
    prefix = "/news"
    
    info(f"--- SETTING UP THE RACE ---\n")
    info(f"Poisoner: {poisoner.name}\n")
    info(f"Producer: {producer.name}\n\n")


    # Start the Real Producer
    producer.cmd(f'echo 0 | ndnpoke {prefix} &')
    producer.cmd(f'nlsrc advertise {prefix}')
    
    # Start the Poisoner
    poisoner.cmd(f'echo 1 | ndnpoke {prefix} &')
    poisoner.cmd(f'nlsrc advertise {prefix}')
    
    info("Waiting for NLSR to sync...\n")
    time.sleep(240) # Let nslr sync

    # The Consumers pull the data for a fixed duration
    end_time = time.time() + run_duration

    while time.time() < end_time:
        consumer = random.choice(unmngd_nodes)
        info(f"Consumer {consumer.name} is sending Interest for {prefix}\n")
        result = consumer.cmd(f'ndnpeek -p {prefix}')
        info(f" got: {result.strip()}\n")

        time.sleep(random.uniform(0.2, 2.0))

    # Final check to see which packet the consumers are getting
    with open(CSV_FILE, 'a') as f:
        writer = csv.writer(f)
        for consumer in unmngd_nodes:
            info(f"Consumer {consumer.name} is sending final Interest for {prefix}")
            result = consumer.cmd(f'ndnpeek -p {prefix}')
            info(f" got: {result.strip()}\n")
            writer.writerow([iteration, consumer.name, result.strip()]) # Mark consumer result as 0 (real) or 1 (poisoned) based on what they got
        writer.writerow([iteration, producer.name, 2]) # Mark producer as 2 for reference
        writer.writerow([iteration, poisoner.name, 3]) # Mark poisoner as 3 for reference
    
    ndn.stop()

    return

OUTPUT_DIR = "/mini-ndn/results/scenario2"
CSV_FILE = f"{OUTPUT_DIR}/sc2_results.csv"

if __name__ == '__main__':
    setLogLevel('info')

    # Setup output directory and CSV file
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    with open(CSV_FILE, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(["Iteration", "Consumer", "Result"])

    iterations = 10
    node_count = 10
    run_duration = 600 # seconds

    for i in range(1, iterations + 1):
        run_trial(i, node_count, run_duration)