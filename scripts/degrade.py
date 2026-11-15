"""Makes one etcd node slow on purpose, using Docker

  CPU: docker update --cpus <value> <node>
  Network: tc netem (delay) inside the node's network, through the nicolaka/netshoot container

Usage:
  python scripts/degrade.py --node etcd1 --scenario net-gradual
  python scripts/degrade.py --node etcd1 --scenario reset
"""
import argparse
import csv
import random
import subprocess
import time

STEP_SECONDS = 10 # how long each step of a gradual scenario lasts
NET_STEPS_MS = [10, 20, 40, 60, 80, 100, 150, 200] # network delay added at each step
CPU_STEPS = [1.0, 0.5, 0.25, 0.1, 0.05, 0.02, 0.01] # CPU limit at each step (1.0 = one full core)

# How many seconds each scenario lasts
SCENARIO_LENGTH = {
    "net-gradual": STEP_SECONDS * len(NET_STEPS_MS),
    "net-sudden": 80,
    "cpu-gradual": STEP_SECONDS * len(CPU_STEPS),
    "cpu-sudden": 80,
    "spikes": 80,
}


def docker(*args):
    return subprocess.run(["docker", *args], capture_output=True, text=True)


def tc(node, *args):
    """Runs a tc command inside the network of the given node."""
    return docker("run", "--rm", "--net", f"container:{node}", "--cap-add", "NET_ADMIN",
                  "nicolaka/netshoot", "tc", *args)


def set_delay(node, ms):
    tc(node, "qdisc", "replace", "dev", "eth0", "root", "netem", "delay", f"{ms}ms")


def remove_delay(node):
    tc(node, "qdisc", "del", "dev", "eth0", "root")


def all_cpus():
    return docker("info", "--format", "{{.NCPU}}").stdout.strip()


def set_cpu(node, cpus):
    docker("update", "--cpus", str(cpus), node)


def reset(node):
    """Brings the node back to normal: no network delay, all CPUs."""
    remove_delay(node)
    set_cpu(node, all_cpus())


def run(node, scenario, log_path=None):
    """Applies a scenario to the node and writes every change to a CSV file."""
    log_file = open(log_path, "w", newline="") if log_path else None
    log = csv.writer(log_file) if log_file else None
    if log:
        log.writerow(["timestamp", "action", "value"])

    def record(action, value):
        print(f"{time.strftime('%H:%M:%S')} {node}: {action} {value}")
        if log and log_file:
            log.writerow([f"{time.time():.3f}", action, value])
            log_file.flush()

    start = time.time()
    if scenario == "net-gradual":
        for ms in NET_STEPS_MS:
            set_delay(node, ms)
            record("net_delay_ms", ms)
            time.sleep(STEP_SECONDS)
    elif scenario == "net-sudden":
        set_delay(node, 150)
        record("net_delay_ms", 150)
        time.sleep(SCENARIO_LENGTH[scenario])
    elif scenario == "cpu-gradual":
        for cpus in CPU_STEPS:
            set_cpu(node, cpus)
            record("cpus", cpus)
            time.sleep(STEP_SECONDS)
    elif scenario == "cpu-sudden":
        set_cpu(node, 0.01)
        record("cpus", 0.01)
        time.sleep(SCENARIO_LENGTH[scenario])
    elif scenario == "spikes":
        # short random slowdowns that should NOT trigger a leader change
        while time.time() - start < SCENARIO_LENGTH[scenario] - 5:
            time.sleep(random.uniform(5, 12))
            set_delay(node, 150)
            record("net_delay_ms", 150)
            time.sleep(2)
            remove_delay(node)
            record("net_delay_ms", 0)
    reset(node)
    record("reset", "")
    if log_file:
        log_file.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--node", default="etcd1")
    p.add_argument("--scenario", choices=list(SCENARIO_LENGTH) + ["reset"], required=True)
    p.add_argument("--out", default=None, help="optional CSV file where the changes are written")
    args = p.parse_args()
    if args.scenario == "reset":
        reset(args.node)
        print(f"{args.node} is back to normal")
    else:
        run(args.node, args.scenario, args.out)


if __name__ == "__main__":
    main()