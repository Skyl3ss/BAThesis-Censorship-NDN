import time
from ndn.experiments.experiment import Experiment

def run_experiment(net):
    # 1. Setup Actors
    # In a Powerlaw graph, lower IDs (n0, n1) are usually the big Hubs
    consumer = net.hosts[0]    # The victim
    poisoner = net.hosts[1]    # The 'closer' Malicious Hub
    producer = net.hosts[40]   # The 'distant' Real Producer
    
    prefix = "/race/data"
    
    print(f"--- SETTING UP THE RACE ---")
    print(f"Consumer: {consumer.name}")
    print(f"Poisoner: {poisoner.name} (Closer)")
    print(f"Producer: {producer.name} (Distant)")

    # 2. Start the Real Producer (Distant)
    producer.cmd(f'echo "REAL_DATA_FROM_PRODUCER" | ndnpoke {prefix} &')
    
    # 3. Start the Poisoner (Close)
    # We use a slight delay or just rely on the topology distance
    poisoner.cmd(f'echo "POISONED_DATA_FROM_HUB" | ndnpoke {prefix} &')
    
    time.sleep(2) # Let the 'pokes' settle in the local Content Stores

    # 4. The Consumer pulls the data
    print(f"\nConsumer {consumer.name} is sending Interest for {prefix}...")
    
    # We use ndnpeek to see the exact string returned
    result = consumer.cmd(f'ndnpeek -p {prefix}')
    
    print("\n" + "="*30)
    print(f"RACE RESULT: {result.strip()}")
    print("="*30)

    # 5. The "Legacy" Check: Is the cache now stuck?
    print("\nChecking if the Hub's cache is poisoned for others...")
    # Pick a random neighbor of the consumer
    neighbor = net.hosts[5]
    res2 = neighbor.cmd(f'ndnpeek -p {prefix}')
    print(f"Neighbor {neighbor.name} received: {res2.strip()}")

    if "POISONED" in result:
        print("\nConclusion: The Poisoner won the race due to proximity.")
    else:
        print("\nConclusion: The Real Producer won (unlikely in this setup!)")

if __name__ == '__main__':
    pass