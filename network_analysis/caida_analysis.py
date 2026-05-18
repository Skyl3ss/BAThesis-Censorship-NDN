import collections
import networkx as nx
import random
import statistics
import os
import igraph as ig
import numpy as np
from scipy.sparse.linalg import eigsh
import scipy.sparse as sp



def load_as_graph_advanced(file_path):
    """
    Builds the graph with directed P2C and bidirectional P2P edges.
    """
    G = nx.DiGraph()
    print(f"Loading graph from {file_path}...")
    
    with open(file_path, 'r') as f:
        for line in f:
            if line.startswith('#'): continue
            parts = line.strip().split('|')
            if len(parts) < 3: continue
            
            u, v = parts[0], parts[1]
            try:
                rel = int(parts[2])
            except ValueError: continue
            
            # -1: u is provider of v (u -> v)
            if rel == -1:
                G.add_edge(u, v, type='customer') 
            
            # 0: peer (u <-> v)
            elif rel == 0:
                G.add_edge(u, v, type='peer')
                G.add_edge(v, u, type='peer')

    # --- STATISTICS PRINT ---
    num_nodes = G.number_of_nodes()
    num_edges = G.number_of_edges()
    
    # Density = actual edges / possible edges
    density = nx.density(G) if num_nodes > 1 else 0

    print("-" * 30)
    print(f"GRAPH LOADED SUCCESSFULLY")
    print(f"Nodes: {num_nodes:,}")
    print(f"Edges: {num_edges:,}")
    print(f"Density: {density:.6f}")
    print("-" * 30)
                
    return G

def analyze_weakest_links(G, sample_size=50):
    """
    Calculates Betweenness Centrality to find 'Traffic Funnels'.
    Uses k-sampling approximation to be fast.
    """
    print(f"\n[1/5] Calculating 'Traffic Funnels' (Betweenness Centrality)...")
    print(f"      (Using approximation with k={sample_size} samples)")
    
    # This finds nodes that act as bridges for the most traffic
    centrality = nx.betweenness_centrality(G, k=sample_size, normalized=True)
    
    # Sort and get top 5
    top_bridges = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:5]
    
    print("\n--- TOP 5 TRAFFIC CHOKEPOINTS (High Betweenness) ---")
    print("These nodes appear on the most shortest-paths. If they fail, traffic suffers.")
    for asn, score in top_bridges:
        print(f"AS {asn:<6} | Score: {score:.5f}")

def analyze_customer_depth(G):
    """
    Approximates 'Tier 1' status by counting direct customers (Out-Degree in P2C).
    """
    print(f"\n[2/5] Identifying 'High Level' Providers (Degree Centrality)...")
    
    # We only care about edges where the node is the Provider
    provider_scores = {}
    for n in G.nodes():
        # Count edges where n points to neighbor AND it's a customer link
        customers = [nbr for nbr in G.successors(n) if G[n][nbr]['type'] == 'customer']
        provider_scores[n] = len(customers)
        
    top_providers = sorted(provider_scores.items(), key=lambda x: x[1], reverse=True)[:5]
    
    print("\n--- TOP 5 PROVIDERS (Most Direct Customers) ---")
    for asn, count in top_providers:
        print(f"AS {asn:<6} | Customers: {count}")
        
    return [asn for asn, count in top_providers] # Return top ASNs for next step

def analyze_path_lengths(G, top_asns, sample_size=100):
    """
    Calculates how many 'hops' it takes for random small networks 
    to reach the big Tier 1 providers.
    """
    print(f"\n[3/5] Analyzing Path Lengths for Consumers...")
    
    # Identify 'leaf' nodes (ASNs with no customers, likely regular ISPs or companies)
    # This is a heuristic: If out_degree (customer links) is 0, you are a consumer.
    leaf_nodes = [n for n in G.nodes() if G.out_degree(n) == 0]
    
    if not leaf_nodes:
        print("No leaf nodes found (check graph data).")
        return

    # Sample random consumers
    sample_leaves = random.sample(leaf_nodes, min(len(leaf_nodes), sample_size))
    path_lengths = []

    print(f"      (Tracing paths from {len(sample_leaves)} random customers to Top 5 Providers)")

    for leaf in sample_leaves:
        for target in top_asns:
            try:
                # We search path leaf -> target. 
                # Note: In reality, traffic flows UP to providers, so we traverse the graph in reverse
                # or assume the graph edges are Provider->Customer. 
                # To find path Customer->Provider, we look for path in the REVERSE graph.
                # However, since we defined -1 as Prov->Cust, we actually need to traverse UP.
                # Shortest path in Undirected view is often used for simple 'hop count'.
                path = nx.shortest_path_length(G, source=target, target=leaf)
                path_lengths.append(path)
            except nx.NetworkXNoPath:
                continue

    if path_lengths:
        avg_hops = statistics.mean(path_lengths)
        print(f"\n--- AVERAGE PATH ANALYSIS ---")
        print(f"Average Hops from Top Tier to Customer: {avg_hops:.2f}")
        print(f"Min Hops: {min(path_lengths)}")
        print(f"Max Hops: {max(path_lengths)}")
    else:
        print("Could not find connected paths between samples and core.")



def analyze_algebraic_connectivity(G, sample_size=3000, trials=5):
    """
    Computes algebraic connectivity (lambda_2) of the AS graph.
    """
    print(f"\n[4/5] Computing Algebraic Connectivity (Spectral Robustness)...")

    try:
        """
        Safe approximation of algebraic connectivity for massive graphs.
        """
        Gu = G.to_undirected()
        Gu.remove_nodes_from(list(nx.isolates(Gu)))
        nodes = list(Gu.nodes())

        if Gu.number_of_nodes() < 2:
            print("Graph too small for algebraic connectivity.")
            return None

        estimates = []

        print(f"\nApproximating λ₂ using {trials} samples of {sample_size} nodes...")

        for i in range(trials):

            # Random BFS sample to get a connected subgraph
            start_node = random.choice(nodes)
            sample_nodes = {start_node}
            queue = collections.deque([start_node])
        
            while len(sample_nodes) < sample_size and queue:
                current = queue.popleft()
                neighbors = list(Gu.neighbors(current))
                random.shuffle(neighbors) # Adds variety to the sample
                for n in neighbors:
                    if n not in sample_nodes:
                        sample_nodes.add(n)
                        queue.append(n)
                        if len(sample_nodes) >= sample_size:
                            break

            H = Gu.subgraph(sample_nodes)

            if not nx.is_connected(H):
                H = H.subgraph(max(nx.connected_components(H), key=len))

            Gi = ig.Graph.from_networkx(H)
            L_list = Gi.laplacian(normalized=True)

            # Convert explicitly to SciPy sparse CSR
            L = sp.csr_matrix(L_list)

            # Compute two smallest eigenvalues
            vals = eigsh(
                L,
                k=2,
                which="SM",
                tol=1e-3,        # relaxed tolerance = safer & faster
                maxiter=500,
                return_eigenvectors=False
            )
            vals.sort()

            estimates.append(vals[1])
            print(f"  Trial {i+1}: λ₂ ≈ {vals[1]:.10f}")

        lambda2avg = float(np.mean(estimates))

        print("\n--- ALGEBRAIC CONNECTIVITY ---")
        print(f"λ₂ (Estimated Algebraic Connectivity): {lambda2avg:.10f}")

        # Cheeger bounds
        h_lower = lambda2avg / 2
        h_upper = (2 * lambda2avg) ** 0.5

        print("\n--- CHEEGER BOUNDS (from λ₂) ---")
        print(f"Lower bound: {h_lower:.10f}")
        print(f"Upper bound: {h_upper:.10f}")

    except nx.NetworkXError as e:
        print(f"Error computing algebraic connectivity: {e}")
        return None



def analyze_average_degree(G):
    """
    Computes average, max, and min degree statistics for the AS graph.
    """
    print(f"\n[5/5] Computing Degree Statistics...")
    
    # Use undirected graph to count all unique neighbors
    Gu = G.to_undirected()
    Gu.remove_nodes_from(list(nx.isolates(Gu)))

    if Gu.number_of_nodes() > 0:
        degrees = dict(Gu.degree())
        degree_values = list(degrees.values())
        
        avg_degree = sum(degree_values) / Gu.number_of_nodes()
        max_degree = max(degree_values)
        min_degree = min(degree_values)
        
        # Find which AS has the most connections
        top_node = max(degrees, key=degrees.get)
    else:
        avg_degree = max_degree = min_degree = 0
        top_node = "N/A"

    print("\n--- DEGREE DISTRIBUTION ---")
    print(f"Avg Degree:         {avg_degree:.2f}")
    print(f"Max Degree (Hub):   {max_degree} (Node: AS {top_node})")
    print(f"Min Degree (Leaf):  {min_degree}")




# --- MAIN EXECUTION ---
if __name__ == "__main__":

    # Config
    FILE_PATH = os.path.join(os.path.dirname(__file__), "20251201.as-rel.txt")
    # CAIDA dataset file (download and place in same folder as this script not provided due to licensing,
    # but can be obtained from CAIDA's AS Relationships dataset: https://publicdata.caida.org/datasets/as-relationships/serial-1/)

    # Run Analysis
    if os.path.exists(FILE_PATH):
        G = load_as_graph_advanced(FILE_PATH)
        
        analyze_weakest_links(G,sample_size=50)
        top_tier = analyze_customer_depth(G)
        analyze_path_lengths(G, top_tier, sample_size=100)
        analyze_algebraic_connectivity(G, sample_size=1000, trials=20)
        analyze_average_degree(G)
        
    else:
        print("File not found.")

