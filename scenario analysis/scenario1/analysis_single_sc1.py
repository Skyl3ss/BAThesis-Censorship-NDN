import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# 1. Load the data
df = pd.read_csv('sc1_results.csv')

# 2. Setup the figure with two subplots (RTT and Packet Loss)
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
sns.set_theme(style="whitegrid")

# --- Plot 1: Average RTT ---
# Filter out the 0 values (failures) so they don't tank the line chart
rtt_data = df[df['Avg_RTT'] > 0]
sns.lineplot(data=rtt_data, x='Step', y='Avg_RTT', marker='o', ax=ax1, color='b', linewidth=2)
ax1.set_title('Impact of Node Censorship on Network Latency (RTT)', fontsize=14, fontweight='bold')
ax1.set_ylabel('Avg RTT (ms)', fontsize=12)
ax1.grid(True, linestyle='--', alpha=0.7)

# --- Plot 2: Packet Loss ---
sns.barplot(data=df, x='Step', y='Packet_Loss', ax=ax2, palette='Reds_d', alpha=0.8)
ax2.set_title('Packet Loss Percentage per Censorship Step', fontsize=14, fontweight='bold')
ax2.set_ylabel('Packet Loss (%)', fontsize=12)
ax2.set_xlabel('Censorship Step (Nodes Removed)', fontsize=12)
ax2.set_ylim(0, 110)

# 3. Add "The Cliff" Annotation
# Based on your data, Step 20 is where the network permanently dies
ax2.annotate('Total Network Collapse', xy=(20, 100), xytext=(25, 80),
             arrowprops=dict(facecolor='black', shrink=0.05),
             fontsize=12, color='red', fontweight='bold')

# 4. Highlight the "Near-Miss" at Step 8
ax2.annotate('Path Instability', xy=(8, 60), xytext=(1, 80),
             arrowprops=dict(facecolor='orange', shrink=0.05),
             fontsize=10, color='orange')

plt.tight_layout()
plt.savefig('censorship_analysis.png', dpi=300)
plt.show()