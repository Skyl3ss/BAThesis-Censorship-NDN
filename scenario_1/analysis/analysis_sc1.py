import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Load the data
df = pd.read_csv('.\sc1_results.csv')

# Determine max step to keep the X-axis consistent across both plots
max_step = df['Step'].max()
sns.set_theme(style="whitegrid")

# --- GRAPH 1: RTT (Stand-alone Figure) ---
plt.figure(figsize=(12, 6))

# Filter for RTT > 0 so lines stop when connection is lost
active_rtt = df[df['Avg_RTT'] > 0]

sns.lineplot(
    data=active_rtt, 
    x='Step', 
    y='Avg_RTT', 
    hue='Trial', 
    palette='tab10', 
    alpha=0.7, 
    linewidth=2
)

plt.title('Network Latency (RTT) Across 10 Trials', fontsize=14, fontweight='bold')
plt.ylabel('Avg RTT (ms)', fontsize=12)
plt.xlabel('Censorship Step', fontsize=12)

# Start Y at 0 and keep X axis for the full range
plt.ylim(bottom=0)
plt.xlim(0, max_step)

# Place legend outside to keep the plot clean
plt.legend(title='Trial', bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()
plt.savefig('rtt_plot.png', dpi=300)
plt.show()


# --- GRAPH 2: Packet Loss Heatmap (Stand-alone Figure) ---
plt.figure(figsize=(12, 6))

# Pivot the data so: Rows = Trials, Columns = Steps
loss_pivot = df.pivot(index="Trial", columns="Step", values="Packet_Loss")

sns.heatmap(
    loss_pivot, 
    cmap='YlOrRd', 
    cbar_kws={'label': 'Packet Loss %'}, 
    linewidths=.1
)

plt.title('Connectivity Status (Packet Loss Heatmap)', fontsize=14, fontweight='bold')
plt.ylabel('Trial Number', fontsize=12)
plt.xlabel('Censorship Step', fontsize=12)
plt.tight_layout()
plt.savefig('packet_loss_heatmap.png', dpi=300)
plt.show()