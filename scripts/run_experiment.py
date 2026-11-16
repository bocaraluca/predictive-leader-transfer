"""Runs one experiment: normal traffic, then a slow leader, with one controller mode

Example:
  python scripts/run_experiment.py --scenario net-gradual --mode predictive --rep 1
"""
import argparse
import json
import os
import subprocess
import sys
import time

import degrade
from common import NODES, find_leader, transfer_leadership

HERE = os.path.dirname(os.path.abspath(__file__))
SLOW_NODE = "etcd1" # the node that will be slowed down (made leader before each run)


def make_leader(node):
    """Moves the leadership to the given node"""
    for _ in range(5):
        leader, ids = find_leader()
        if leader == node:
            return True
        if leader is not None:
            transfer_leadership(leader, node, ids)
        time.sleep(2)
    return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", choices=list(degrade.SCENARIO_LENGTH), required=True)
    p.add_argument("--mode", choices=["none", "reactive", "predictive"], required=True)
    p.add_argument("--rep", type=int, default=1)
    p.add_argument("--warmup", type=int, default=30)
    p.add_argument("--tail", type=int, default=30)
    args = p.parse_args()

    out = os.path.join("results", args.scenario, f"{args.mode}_rep{args.rep}")
    os.makedirs(out, exist_ok=True)

    print("Resetting all nodes ...")
    for node in NODES:
        degrade.reset(node)
    if not make_leader(SLOW_NODE):
        sys.exit(f"Could not make {SLOW_NODE} the leader, check the cluster.")
    time.sleep(2)

    total = args.warmup + degrade.SCENARIO_LENGTH[args.scenario] + args.tail
    followers = ",".join(url for name, url in NODES.items() if name != SLOW_NODE)
    print(f"Running {args.scenario} / {args.mode} / rep {args.rep} for {total}s -> {out}")

    workload = subprocess.Popen([sys.executable, os.path.join(HERE, "workload.py"),
                                 "--duration", str(total), "--endpoints", followers,
                                 "--out", os.path.join(out, "workload.csv")])
    controller = subprocess.Popen([sys.executable, os.path.join(HERE, "controller.py"),
                                   "--mode", args.mode, "--duration", str(total), "--out", out])

    meta = {"scenario": args.scenario, "mode": args.mode, "rep": args.rep,
            "slow_node": SLOW_NODE, "start": time.time()}
    time.sleep(args.warmup)
    meta["degradation_start"] = time.time()
    degrade.run(SLOW_NODE, args.scenario, os.path.join(out, "degrade.csv"))
    meta["degradation_end"] = time.time()

    workload.wait()
    controller.wait()
    meta["end"] = time.time()
    with open(os.path.join(out, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print("Done.")


if __name__ == "__main__":
    main()