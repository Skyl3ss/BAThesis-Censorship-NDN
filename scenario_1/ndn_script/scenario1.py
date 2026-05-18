import time
import sys
import os
import random
import re
import csv
from minindn.minindn import Minindn
from minindn.apps.app_manager import AppManager
from minindn.apps.nfd import Nfd
from minindn.apps.nlsr import Nlsr
from mininet.log import setLogLevel, info
from minindn.util import MiniNDNCLI, getPopen

OUTPUT_DIR = "/mini-ndn/results/scenario1"

def prepare_topology(node_count):
    info(f"\n--- Creating Topology for next run ---\n")

    original_topo = "topologies/custom/sc1_n50_caida_analysis.conf"
    #original_topo = "topologies/custom/caida_analysis.conf" #Used for Debug with less nodes
    active_topo = "topologies/active/active_experiment.conf"

    with open(original_topo, 'r') as f:
        lines = f.readlines()

    # Identify entry for router and consumer
    entry_id = random.randint(0, node_count-1)
    entry_node = f"n{entry_id}"

    new_lines = []
    for line in lines:
        new_lines.append(line)
        if "[nodes]" in line:
            new_lines.append("monrouter: _\n")
            new_lines.append("consumer: _\n")
    
    # Append the links for the tail
    new_lines.append(f"consumer:monrouter delay=10ms bw=10\n")
    new_lines.append(f"monrouter:{entry_node} delay=10ms bw=100\n")

    with open(active_topo, 'w') as f:
        f.writelines(new_lines)

    info(f"Topology prepared with entry node: {entry_node}\n")

    return active_topo, entry_node

def run_trial(trial_num, topo_file, entry_node_name, num_censored):
    info(f"\n--- STARTING TRIAL {trial_num} (Censoring {num_censored} nodes) ---\n")
    Minindn.cleanUp()
    ndn = Minindn(topoFile=topo_file)
    ndn.start()

    # Setup Nodes
    monitor_router = ndn.net.get('monrouter')
    consumer = ndn.net.get('consumer')
    web_nodes = [n for n in ndn.net.hosts if n.name not in ['monrouter', 'consumer']]
    producer = random.choice(web_nodes)

    # Start NDN
    info('Starting nfd and nlsr on nodes\n')
    AppManager(ndn, ndn.net.hosts, Nfd)
    AppManager(ndn, ndn.net.hosts, Nlsr)

    # Advertise the prefix and wait for NLSR to sync
    info("Advertising prefix\n")
    prefix = "/news"
    producer.cmd(f'nlsrc advertise {prefix}')
    info(f"Starting ping server on {producer.name}...\n")
    getPopen(producer, f"ndnpingserver {prefix}")
    info("Waiting 120s for convergence\n")
    time.sleep(120)
    

    # Get the list of candidate nodes for censorship (excluding producer, consumer, entry node, and monitor)
    chaos_candidates = [n for n in web_nodes if n != producer and n != consumer and n != monitor_router and n.name != entry_node_name]
    random.shuffle(chaos_candidates)

    # Set the defualt stratgey to prevent network storms
    for node in ndn.net.hosts:
        node.cmd(f'nfdc strategy set / /localhost/nfd/strategy/asf')


    # Debug Staments
    if DEBUG:
        debug_file_consumer = f"{OUTPUT_DIR}/consumer_debug.txt"
        with open(debug_file_consumer, "w") as f:
            f.write("=== NLSR Status ===\n")
            f.write(consumer.cmd('nlsrc status') + "\n")
            f.write("=== FIB List ===\n")
            f.write(consumer.cmd("nfdc fib list") + "\n")

        debug_file_monitor = f"{OUTPUT_DIR}/monitor_debug.txt"
        with open(debug_file_monitor, "a") as f:
            f.write("=== NLSR Status ===\n")
            f.write(monitor_router.cmd('nlsrc status') + "\n")
            f.write("=== FIB List ===\n")
            f.write(monitor_router.cmd("nfdc fib list") + "\n")
        
        test_node = ndn.net.get('n0')
        debug_file_node = f"{OUTPUT_DIR}/node_debug_before.txt"
        with open(debug_file_node, "a") as f:
            f.write("=== NLSR Status ===\n")
            f.write(test_node.cmd('nlsrc status') + "\n")
            f.write("=== FIB List ===\n")
            f.write(test_node.cmd("nfdc fib list") + "\n")

    
    # We will perform a ping test after EVERY node is censored to track degradation
    for step in range(num_censored + 1):
        if step == 0:
            info(">>> Step 0: Measuring Baseline <<<\n")
        else:
            censor = chaos_candidates[step-1]
            info(f">>> Step {step}: CENSORING {prefix} ON {censor.name} <<<\n")
            
            # Applying the content filte to simulate censorship
            # 1. Remove all existing routes for this prefix so the node "forgets" how to reach the producer
            censor.cmd(f'nlsrc withdraw {prefix}')
            faces_output = censor.cmd(f"nfdc fib list | grep -w '{prefix}' | grep -oP 'faceid=\\K\\d+'").split()

            for fid in faces_output:
                # Remove the 'good' routes
                info(fid)
                censor.cmd(f"nfdc route remove {prefix} {fid} origin nlsr")

            censor.cmd(f'nfdc strategy set {prefix} /localhost/nfd/strategy/best-route')  

            # 2. Add the blackhole route with the absolute highest priority (cost 0)
            censor.cmd(f'nfdc route add {prefix} internal:// cost 0')

            # 3. VERIFY: Print the FIB immediately to ensure it stuck
            time.sleep(2) #short delay to allow the route changes to take effect before checking
            info(f"VERIFYING CENSORSHIP ON {censor.name}: \n {censor.cmd('nfdc fib list | grep ' + prefix)}")


        # Run a short ping test (10 pings) to see the current state
        log_file = f"{OUTPUT_DIR}/trial_{trial_num}_step_{step}.txt"
        info(f"Pinging prrefix {prefix}\n")
        # Using -c 10 to get a quick "health check"
        result = consumer.cmd(f'ndnping -c 10 -i 1000 {prefix}')


        # --- PARSING LOGIC ---
        # Default values in case of complete failure (100% loss or no response)
        avg_rtt = 0
        loss_pct = 100
        
        # Regex to find the avg value in the summary line
        rtt_match = re.search(r'min/avg/max/mdev = [\d.]+/([\d.]+)/', result)
        loss_match = re.search(r'(\d+)% lost', result)
        
        if rtt_match:
            avg_rtt = float(rtt_match.group(1))
        if loss_match:
            loss_pct = int(loss_match.group(1))
        
        censor_name = censor.name if step > 0 else "None"

        # Write to Master CSV
        with open(CSV_FILE, 'a') as f:
            writer = csv.writer(f)
            writer.writerow([trial_num, step, censor_name, avg_rtt, loss_pct])

        info(f"Done (Avg: {avg_rtt}ms, Loss: {loss_pct}%)\n\n")
        time.sleep(10)
        
    
        if DEBUG:

            with open(log_file, "w") as f:
                f.write(result)
            
            # Check for failure in console
            if "timeout" in result or "100% packet loss" in result:
                info("NETWORK DEGRADED (Timeouts detected)\n")
            else:
                info("NETWORK HEALTHY\n")
                
            time.sleep(10)


            test_node = ndn.net.get('n0')
            debug_file_node = f"{OUTPUT_DIR}/node_debug_after.txt"
            with open(debug_file_node, "a") as f:
                f.write("=== NLSR Status ===\n")
                f.write(test_node.cmd('nlsrc status') + "\n")
                f.write("=== FIB List ===\n")
                f.write(test_node.cmd("nfdc fib list") + "\n")

            #MiniNDNCLI(ndn.net)


    ndn.stop()

    return

OUTPUT_DIR = "/mini-ndn/results/scenario1"
DEBUG = False
CSV_FILE = f"{OUTPUT_DIR}/master_results.csv"

if __name__ == '__main__':
    setLogLevel('info')

    # Setup output directory and master CSV file
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    with open(CSV_FILE, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(["Trial", "Step", "Censored_Node", "Avg_RTT", "Packet_Loss"])


    # Configuration for the experiment
    iterations = 1
    node_count = 50
    num_censored = node_count - 2 # We don't censor the producer and entry node otherwise we would immediately break the network

    for i in range(1, iterations + 1):
        topo, entry = prepare_topology(node_count)
        run_trial(i, topo, entry, num_censored)