# Predictive Leader Transfer for etcd

*Predicting slow leaders – leadership transfer against gray failures in Raft-based distributed systems*.

## The problem

In Raft, every write goes through the leader. If the leader becomes slow but still sends heartbeats, the cluster does not elect a new one, so every write becomes slow. In etcd, adding a 100 ms network delay to the leader raises the write latency from about 49 ms to about 208 ms, and the leader does not change.

## The idea

An external controller measures every second how fast each node answers. It learns the normal latency of the leader, follows its trend with a linear regression and, when it predicts that the leader will become slow, moves the leadership to the fastest follower using etcd's `move-leader`. etcd is not modified and no node is restarted.

Three variants are compared:
- **none** – no action (default etcd behaviour)
- **reactive** – moves the leader after it has been slow for 5 seconds
- **predictive** – moves the leader when the trend predicts it will become slow

## Results

Network delay on the leader growing from 10 to 200 ms, 3 repetitions per variant:

| Variant | p99 latency | Slow seconds | First transfer |
|---|---|---|---|
| none | 421.8 ms | 51 | – |
| reactive | 84.1 ms | 0 | 20.6 s |
| predictive | 74.7 ms | 0 | 9.7 s* |

\* valid runs only; one run out of three was a false alarm.

## Repository structure

```
docker-compose.yml     3-node etcd cluster
scripts/
  workload.py          writes into etcd and records the latency of every write
  common.py            node status, finding the leader, leadership transfer
  degrade.py           slows down a node (network delay or CPU limit)
  controller.py        the controller (none / reactive / predictive)
  run_experiment.py    runs one complete experiment
  analyze.py           metrics and graphs for all runs of a scenario
results/               raw data, summary.csv and graphs
report/                the research report (LaTeX + PDF)
```

## How to run

Requirements: Docker Desktop and Python 3.

```
docker compose up -d
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

One experiment:
```
python scripts/run_experiment.py --scenario net-gradual --mode predictive --rep 1
```
- scenarios: `net-gradual`, `net-sudden`, `cpu-gradual`, `cpu-sudden`, `spikes`
- modes: `none`, `reactive`, `predictive`

Analysis and graph:
```
python scripts/analyze.py --scenario net-gradual --plot-rep 2
```

If a node stays slow after an experiment:
```
python scripts/degrade.py --node etcd1 --scenario reset
```