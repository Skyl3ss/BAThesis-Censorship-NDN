import time
import subprocess
from ndn.experiments.experiment import Experiment

def run_experiment(net):
    # Setup actors
    consumer = net.hosts[0]
    poisoner = net.hosts[1]
    producer = net.hosts[2]
    
    prefix = "/legal/news"

    print("\n--- PHASE 1: Security Bootstrapping ---")
    
    # Create a legitimate identity for the producer
    print(f"Creating legitimate identity on {producer.name}...")
    producer.cmd('ndnsec-key-gen /legal/news > producer.cert')
    # Set this as the default identity so ndnpoke uses it
    producer.cmd('ndnsec-set-default /legal/news')

    # Create a malicious identity for the poisoner
    print(f"Creating malicious identity on {poisoner.name}...")
    poisoner.cmd('ndnsec-key-gen /hacker/news > hacker.cert')
    poisoner.cmd('ndnsec-set-default /hacker/news')

    print("\n--- PHASE 2: Starting the Signed Race ---")

    # Producer starts serving signed data
    producer.cmd(f'echo "AUTHENTIC DATA" | ndnpoke {prefix} &')
    
    # Poisoner starts serving signed data (but with the WRONG key)
    poisoner.cmd(f'echo "POISONED DATA" | ndnpoke {prefix} &')
    
    time.sleep(2)

    print("\n--- PHASE 3: Consumer Verification ---")
    
    # Consumer pulls data. -p for print, -v for verbose (shows KeyLocator)
    # We use 'ndnpeek -v' to see which key was used
    output = consumer.cmd(f'ndnpeek -v -p {prefix}')
    
    print("\n" + "="*50)
    print("INCOMING PACKET ANALYSIS:")
    print(output)
    print("="*50)

    # Logic to check if the consumer was 'fooled'
    if "/hacker/news" in output:
        print("\nRESULT: Consumer received the Poisoned packet!")
        print("REASON: Proximity won. Consumer has no Trust Schema to reject it yet.")
    elif "/legal/news" in output:
        print("\nRESULT: Consumer received Authenticated data!")
        print("REASON: The Producer won the race (rare) or cache was clear.")
    else:
        print("\nRESULT: Packet received but signature unknown.")

if __name__ == '__main__':
    pass