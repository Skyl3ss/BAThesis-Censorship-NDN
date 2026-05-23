# NDN Network Analysis on CAIDA Topology

A project for analyzing Named Data Networking (NDN) censorship with topologies derived from the CAIDA AS-level dataset. Uses Mini-NDN to simulate network behavior across multiple scenarios.

## Quick Start

### 1. Install Mini-NDN

Mini-NDN requires Ubuntu Linux 20.04. To install Mini-NDN follow the directions to install the docker version on
https://minindn.memphis.edu/install.html#building-your-own-docker-image .

### 2. Get CAIDA Dataset

The project uses CAIDA AS relationship data. Download it under:
https://www.caida.org/data/as-relationships/
The file should be named: YYYYMMDD.as-rel.txt.bz2

**File location:** Place the decompressed `.as-rel.txt` file in the `network_analysis/` directory.

### 3. Run Network Analysis

The network analysis step processes the CAIDA data and generates Mini-NDN topology configurations:

```bash
cd network_analysis/

# Analyze CAIDA data and build topology files
python3 caida_analysis.py

# To generate graphs with the collected metrics
python3 graph_build.py
```

### 4. Run Scenarios in Mini-NDN

Each scenario tests different NDN censorship scenarios on a generated topology.
The files used for each Mini-NDN scenario are found in the respective scenario folders. They have to be copied to a respective folder inside the Mini-NDN container before being executed.

#### Running a Scenario

```bash
# Copy scenario script to Mini-NDN
cp scenario_1/ndn_script/scenario1.py /mini-ndn/examples/scenarios/

# Copy topology configuration to Mini-NDN
cp scenario_1/topologies/caida_analysis_n50_sc1.conf /mini-ndn/topologies/custom/

# Run scenario (inside Mini-NDN)
cd /mini-ndn
sudo python3 /mini-ndn/examples/scenarios/scenario_1.py /mini-ndn/topologies/custom/sc1_n50_caida_analysis.conf

# Results are saved to /mini-ndn/results/scenario1/
```

#### Scenario Overview

Each scenario (1-3) performs the following:

1. **Loads the topology** - Reads the CAIDA-based `.conf` file
2. **Configures NDN** - Sets up NFD (Named Data Daemon), NLSR (NDN Link State Routing)
3. **Runs experiments** - Sends Interests and tracks performance
4. **Collects metrics** - Collects metrics and saves results to `results/`

The scenarios differ in:
- **Scenario 1** - Tests basic NDN forwarding with 50 nodes
- **Scenario 2** - Tests with alternative strategy/configurations
- **Scenario 3** - Smaller test with 10 nodes

## Analysis & Results

After running scenarios, analyze results by using the associated analysis script. For this the associated `.csv` file has to be copied into the `analysis/` folder of the respective sceanrio.

```bash
cd scenario_1/analysis/
python3 analysis_sc1.py  # Analyzes performance metrics and generates graphs
```

Results are output to graphs which are saved inside the `analysis/` folder.

## Project Structure

```
.
├── network_analysis/          # CAIDA processing & analysis
│   ├── caida_analysis.py      # Analyzes CAIDA topology
│   ├── graph_build.py         # Generates topologies
│   └── 20251201.as-rel.txt    # CAIDA dataset (download separately)
├── scenario_1/                # First test scenario
│   ├── ndn_script/scenario1.py
│   ├── analysis/analysis_sc1.py
│   └── topologies/caida_analysis_n50_sc1.conf
├── scenario_2/                # Second test scenario
│   ├── ndn_script/scenario2.py
│   ├── analysis/analysis_sc2.py
│   └── topologies/sc2_n50_caida_analysis.conf
└── scenario_3/                # Third test scenario
    ├── ndn_script/scenario3.py
    └── topologies/sc3_n10_caida_analysis.conf
```

## Troubleshooting

- **Mini-NDN requires root/sudo** for network simulation
- **CAIDA file format** - Ensure `.as-rel.txt` is properly decompressed (not `.bz2`)
- **Topology paths** - Scenario scripts reference relative paths; run from Mini-NDN root directory
- **Ensure Enviroment is reset** - Scenario cleanup may not remove all configurations set. To ensure scenarios are tested on clean setups run the following commands beforehand.
```
# sudo rm -rf /tmp/minindn /tmp/n0 /tmp/n1/ /tmp/n2 /tmp/n3
# sudo pkill -f /tmp/n1/consumer && sudo pkill -f /tmp/n1/producer && sudo pkill -f /tmp/n2/producer && sudo pkill -f /tmp/n2/consumer && sudo pkill -f /tmp/n3/producer && sudo pkill -f /tmp/n3/consumer 
```
