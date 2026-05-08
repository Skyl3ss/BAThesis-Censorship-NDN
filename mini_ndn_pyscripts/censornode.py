import time
import sys
import os
import random
from minindn.minindn import Minindn
from minindn.apps.app_manager import AppManager
from minindn.apps.nfd import Nfd
from minindn.apps.nlsr import Nlsr
from mininet.log import setLogLevel, info

OUTPUT_DIR = "/mini-ndn/results"

def run_experiment():
    setLogLevel('info')

    Minindn.cleanUp()
    Minindn.verifyDependencies()
    ndn = Minindn()
    
    # 1. Setup Nodes
    web_nodes = ndn.net.hosts[:]
    entry_point = random.choice(web_nodes)
    monitor_router = ndn.net.addHost('monrouter')
    consumer = ndn.net.addHost('consumer')
    
    ndn.net.addLink(consumer, monitor_router)
    ndn.net.addLink(monitor_router, entry_point)
    
    ndn.start()

    # 2. Start NDN Stack
    info('Starting nfd and nlsr on nodes')
    nfds = AppManager(ndn, ndn.net.hosts, Nfd)
    nlsrs = AppManager(ndn, ndn.net.hosts, Nlsr)

    producer = random.choice([n for n in web_nodes if n != entry_point])

    sleep(90)

    # 3. START PCAP (The "Bulletproof" Version)
    pcap_path = os.path.join(OUTPUT_DIR, "chaos_monitor.pcap")
    
    # -n: No DNS (fast)
    # -i any: All interfaces
    # -U: Packet-buffered (immediate write)
    # -v: Verbose (sometimes helps logging)
    info(f"--- Launching tcpdump on {monitor_router.name} ---\n")
    monitor_router.cmd(f'tcpdump -n -i any -U -w {pcap_path} > {OUTPUT_DIR}/tcpdump_log.txt 2>&1 &')
    
    # Check if it actually started
    time.sleep(2)
    check = monitor_router.cmd('pgrep tcpdump')
    if not check.strip():
        info("WARNING: tcpdump failed to start! Check /mini-ndn/results/tcpdump_log.txt\n")

    # 4. Routing Setup
    producerPrefix = "/news"

    producer.cmd('nlsrc advertise {}'.format(producerPrefix))
    sleep(5) # sleep for routing convergence

    info('Starting consumer and producer application')
    producer.cmd("echo 'HELLO WORLD' | ndnpoke {} &> producer.log &".format(producerPrefix))
    consumer.cmd("ndnpeek -p {} &> consumer.log &".format(producerPrefix))

    info("Waiting 60s for NLSR...\n")
    time.sleep(60)

    # 5. Traffic & Chaos
    producer.cmd('ndnpingserver /news &')
    time.sleep(2)
    info("Starting Traffic...\n")
    consumer.cmd(f'ndnping -c 50 /news > {OUTPUT_DIR}/ping_log.txt &')

    chaos_candidates = [n for n in web_nodes if n not in [producer, entry_point]]
    random.shuffle(chaos_candidates)

    for victim in chaos_candidates[:2]:
        info(f"!!! CENSORING {victim.name} !!!\n")
        victim.cmd('iptables -I FORWARD -p udp --dport 6363 -j DROP')
        time.sleep(15)

    # 6. Cleanup
    info("--- Shutdown ---\n")
    monitor_router.cmd('pkill -9 tcpdump') # Force kill to flush
    time.sleep(2)
    
    for node in ndn.net.hosts:
        node.cmd('iptables -F')
        
    ndn.stop()
    info(f"Experiment finished. Results in {OUTPUT_DIR}\n")

if __name__ == '__main__':

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    run_experiment()