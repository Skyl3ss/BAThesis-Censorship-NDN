import networkx as nx
import matplotlib.pyplot as plt
import pandas as pd
import re
import os

# --- 1. READ FILES ---
CAIDA_CONF = os.path.join(os.path.dirname(__file__), "sc2_n50_caida_analysis.conf")
SC2_RESULTS = os.path.join(os.path.dirname(__file__), "sc2_results.csv")


with open(CAIDA_CONF, 'r') as f:
    setup_content = f.read()

results_df = pd.read_csv(SC2_RESULTS)


# --- 2. PARSE SETUP.CONF ---
links = []
# Use regex to find the links section and extract node pairs
# This looks for patterns like 'n0:n2'
link_pattern = re.compile(r'(n\d+):(n\d+)')

# We only care about lines after the [links] header
if '[links]' in setup_content:
    links_section = setup_content.split('[links]')[1]
    links = link_pattern.findall(links_section)

# --- 3. PREPARE GRAPH DATA ---
G = nx.Graph()
G.add_edges_from(links)

# Map results (Iteration 1 by default, or you can filter)
# Mapping: 0:real, 1:poisoned, 2:producer, 3:poisoner
node_results = dict(zip(results_df['Consumer'], results_df['Result']))

COLOR_MAP = {
    0: "skyblue",    # Real
    1: "salmon",     # Poisoned
    2: "gold",       # Producer
    3: "crimson"     # Poisoner
}

# Assign colors; default to grey if a node in the config isn't in the results
node_colors = [COLOR_MAP.get(node_results.get(node), "grey") for node in G.nodes()]

# --- 4. VISUALIZATION ---
plt.figure(figsize=(14, 10))

# Layout algorithm
pos = nx.spring_layout(G, k=0.5, seed=42)

# Draw components
nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=600, alpha=0.9)
nx.draw_networkx_edges(G, pos, width=1.0, alpha=0.3, edge_color='gray')
nx.draw_networkx_labels(G, pos, font_size=8, font_weight="bold")

# Legend
from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0], [0], marker='o', color='w', label='Real (0)', markerfacecolor='skyblue', markersize=10),
    Line2D([0], [0], marker='o', color='w', label='Poisoned (1)', markerfacecolor='salmon', markersize=10),
    Line2D([0], [0], marker='o', color='w', label='Producer (2)', markerfacecolor='gold', markersize=10),
    Line2D([0], [0], marker='o', color='w', label='Poisoner (3)', markerfacecolor='crimson', markersize=10)
]
plt.legend(handles=legend_elements, loc='upper right', title="Node Status")

plt.title(f"Network Analysis: {CAIDA_CONF} + {SC2_RESULTS}")
plt.axis('off')

# Save and Show
plt.tight_layout()
plt.savefig('network_analysis_output.png')
print("Graph saved as 'network_analysis_output.png'")
plt.show()
