import csv
import os
import matplotlib.pyplot as plt
import networkx as nx

CONF_PATH = os.path.join(os.path.dirname(__file__), "sc2_n50_caida_analysis.conf")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "sc2_results.csv")
OUTPUT_IMAGE = os.path.join(os.path.dirname(__file__), "sc2_graph.png")

LABEL_MAP = {
    "0": "real",
    "1": "poisoned",
    "2": "producer",
    "3": "poisoner",
}

COLOR_MAP = {
    "0": "#2ca02c",  # green for real
    "1": "#d62728",  # red for poisoned
    "2": "#1f77b4",  # blue for producer
    "3": "#ff7f0e",  # orange for poisoner
}


def read_topology(conf_path):
    nodes = []
    links = []
    active_section = None
    with open(conf_path, "r", encoding="utf-8") as conf_file:
        for raw_line in conf_file:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                active_section = line.lower()
                continue
            if active_section == "[nodes]":
                if ":" in line:
                    node_name = line.split(":", 1)[0].strip()
                    if node_name:
                        nodes.append(node_name)
            elif active_section == "[links]":
                if ":" in line:
                    left, right = line.split(":", 1)
                    right = right.strip().split()[0]
                    links.append((left.strip(), right.strip()))
    return nodes, links


def read_results(results_path):
    results = {}
    with open(results_path, "r", encoding="utf-8") as results_file:
        reader = csv.DictReader(results_file)
        for row in reader:
            consumer = row.get("Consumer") or row.get("consumer")
            result = row.get("Result") or row.get("result")
            if consumer is None or result is None:
                continue
            results[consumer.strip()] = result.strip()
    return results


def build_graph(nodes, links, results):
    graph = nx.Graph()
    graph.add_nodes_from(nodes)
    graph.add_edges_from(links)

    labels = {}
    colors = []
    for node in graph.nodes():
        value = results.get(node, "0")
        labels[node] = f"{node}\n{LABEL_MAP.get(value, 'unknown')}"
        colors.append(COLOR_MAP.get(value, "#7f7f7f"))
    return graph, labels, colors


def draw_graph(graph, labels, colors, output_path):
    plt.figure(figsize=(14, 11))
    pos = nx.spring_layout(graph, seed=42, k=0.35)

    nx.draw_networkx_edges(graph, pos, edge_color="#999999", alpha=0.6)
    nx.draw_networkx_nodes(
        graph,
        pos,
        node_color=colors,
        node_size=650,
        edgecolors="#333333",
        linewidths=0.6,
    )
    nx.draw_networkx_labels(
        graph,
        pos,
        labels=labels,
        font_size=8,
        font_color="#222222",
    )

    legend_handles = [
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=color, markersize=10, label=label)
        for label, color in [
            ("real", COLOR_MAP["0"]),
            ("poisoned", COLOR_MAP["1"]),
            ("producer", COLOR_MAP["2"]),
            ("poisoner", COLOR_MAP["3"]),
        ]
    ]
    plt.legend(handles=legend_handles, loc="upper right", framealpha=0.9, fontsize=18)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


if __name__ == "__main__":

    nodes, links = read_topology(CONF_PATH)
    results = read_results(RESULTS_PATH)
    graph, labels, colors = build_graph(nodes, links, results)
    draw_graph(graph, labels, colors, OUTPUT_IMAGE)
    print(f"Saved visualization to {OUTPUT_IMAGE}")
