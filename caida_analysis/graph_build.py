import networkx as nx
import numpy as np
import matplotlib.pyplot as plt
import random


"""
Generate the graph using the statistics provided from the analysis script
"""
def get_normalized_lambda2(G):
    """Computes the 2nd smallest eigenvalue of the Normalized Laplacian."""
    if not nx.is_connected(G):
        G = G.subgraph(max(nx.connected_components(G), key=len))
    
    if len(G) < 2: return 0
    
    L = nx.normalized_laplacian_matrix(G).todense()
    vals = np.linalg.eigvalsh(L)
    # 2nd smallest eigenvalue
    return vals[1]

def generate_mini_internet_fit(target_nodes=50, target_l2=0.2419, target_hops=2.6):
    """
    Heuristic search using the Holme-Kim algorithm to match CAIDA metrics.
    """
    best_G = None
    best_error = float('inf')

    print(f"Targeting: λ₂ ≈ {target_l2}, Avg Hops ≈ {target_hops}")
    print("Searching parameter space (m = edges, p = clustering)...")

    # m: number of random edges to add for each new node
    # p: probability of adding an extra edge to form a triangle (peering)
    for m in range(2,3):
        for p in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]:
            for _ in range(5): # Multiple seeds per setting
                try:
                    # Holme-Kim Powerlaw Clustered Graph
                    G = nx.powerlaw_cluster_graph(n=target_nodes, m=m, p=p)
                    
                    l2 = get_normalized_lambda2(G)
                    hops = nx.average_shortest_path_length(G) if nx.is_connected(G) else 5.0
                    
                    # Weighting λ₂ more as it defines the "bottleneck" profile
                    error = (abs(l2 - target_l2) * 2) + abs((hops - target_hops) / target_hops)
                    
                    if error < best_error:
                        best_error = error
                        best_G = G
                        best_metrics = (l2, hops, m, p)
                except:
                    continue

    l2, hops, m, p = best_metrics
    print("\n" + "="*40)
    print("MATCH FOUND")
    print("="*40)
    print(f"Nodes: {best_G.number_of_nodes()} | Edges: {best_G.number_of_edges()}")
    print(f"λ₂ (Algebraic Connectivity): {l2:.4f} (Target: {target_l2:.4f})")
    print(f"Avg Path Length:  {hops:.4f} (Target: {target_hops:.2f})")
    print(f"Parameters used:  m={m}, p={p}")
    print("="*40)

    return best_G



"""
Visualization and Exporting functions (graph, caida format, mini ndn config)
"""

def visualize_mini_internet(G):

    # Completly AI writen graph visualization also completely broken

    plt.figure(figsize=(12, 8))
    
    # Calculate layout (spring layout mimics physical forces to show clusters)
    pos = nx.spring_layout(G, k=0.3, iterations=50)
    
    # Node sizing and coloring based on degree (connectivity)
    d = dict(G.degree)
    node_sizes = [v * 100 for v in d.values()]
    node_colors = [v for v in d.values()]

    # Draw the graph
    nodes = nx.draw_networkx_nodes(G, pos, 
                                   node_size=node_sizes, 
                                   node_color=node_colors, 
                                   cmap=plt.cm.plasma,
                                   alpha=0.9)
    
    nx.draw_networkx_edges(G, pos, alpha=0.3, edge_color='gray')
    
    # Label only the big "Tier-1" hubs to keep it clean
    labels = {n: n for n in G.nodes() if d[n] > max(d.values()) * 0.2}
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=10, font_weight='bold') 

    plt.title(f"Topology with 50 Nodes\nλ₂ ≈ {get_normalized_lambda2(G):.4f}")
    plt.colorbar(nodes, label='Degree (Connections)')
    plt.axis('off')
    plt.show()

def export_to_caida(G, filename = "comparison.txt"):
    lines = []
    seen_edges = set()
    
    for u, v in G.edges():
        edge = tuple(sorted((u, v)))
        if edge in seen_edges: continue
        seen_edges.add(edge)

        # Logic: Hubs (smaller indices) are likely providers. 
        # Triangles (formed by 'p') are treated as Peering links.
        # We'll use a 40% probability for Peering to match 'High-Tier' data.
        if random.random() < 0.4:
            rel = 0  # Peer-to-Peer
            lines.append(f"{u}|{v}|{rel}")
        else:
            # Hierarchy: The older node (lower ID) is usually the provider
            provider = min(u, v)
            customer = max(u, v)
            lines.append(f"{provider}|{customer}|-1")

    # 3. Write to file
    with open(filename, "w") as f:
        f.write("\n".join(lines))
    
    print(f"Success! Topology saved to: {filename}")
    print(f"Total Edges written: {len(lines) - 3}")



def export_to_ndn_config(G, filename="caida_analysis.conf"):
    """
    Exports the NetworkX graph to a Mini-NDN config file format.
    """
    with open(filename, "w") as f:
        # 1. Write Nodes
        f.write("[nodes]\n")
        for node in sorted(G.nodes()):
            f.write(f"n{node}: _\n")
        
        # 2. Write Links
        f.write("\n[links]\n")
        seen_edges = set()
        for u, v in G.edges():
            edge = tuple(sorted((u, v)))
            if edge in seen_edges:
                continue
            seen_edges.add(edge)
            
            # Applying static values
            # Format: node1:node2 delay=10ms bw=10
            random_delay = random.randint(10, 100)
            f.write(f"n{u}:n{v} delay={random_delay}ms bw=10\n")

    print(f"\nSuccess! Mini-NDN topology saved to: {filename}")




if __name__ == "__main__":
    # Config Variables
    visualize = True
    generate_caida = False
    generate_ndn_config = True
    Target_Nodes = 10

    mini_ndn_graph = generate_mini_internet_fit(target_nodes = Target_Nodes)

    # Seeing what are the top 3 hubs in this generated graph and how many connections they have
    hubs = sorted(mini_ndn_graph.degree(), key=lambda x: x[1], reverse=True)[:3]
    print(f"\nTier-1 Nodes: {hubs}")

    # Run the visualizer on the graph we just generated
    if visualize:
        visualize_mini_internet(mini_ndn_graph)
    if generate_caida:
        export_to_caida(mini_ndn_graph)
    if generate_ndn_config:
        export_to_ndn_config(mini_ndn_graph)