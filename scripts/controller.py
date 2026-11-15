"""Watches the etcd nodes every second and moves the leadership away from a slow leader.

Modes:
  none        only records the measurements (no action)
  reactive    moves the leader after it has been slow for several seconds
  predictive  moves the leader when the trend of its latency predicts it will become slow
"""
import argparse
import csv
import os
import statistics
import time

from common import NODES, poll_nodes, transfer_leadership


def slope(values):
    """Slope of the least-squares line through the values (one value per second)."""
    n = len(values)
    mean_x = (n - 1) / 2
    mean_y = sum(values) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in enumerate(values))
    den = sum((x - mean_x) ** 2 for x in range(n))
    return num / den


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["none", "reactive", "predictive"], default="none")
    p.add_argument("--duration", type=float, default=180)
    p.add_argument("--out", default="results/controller")
    p.add_argument("--calibration", type=int, default=15, help="seconds used to learn the normal latency")
    p.add_argument("--factor", type=float, default=3.0, help="slow = factor x normal latency")
    p.add_argument("--min-margin", type=float, default=20.0, help="slow also means at least this many ms above normal")
    p.add_argument("--reactive-seconds", type=int, default=5, help="reactive: how long the leader must be slow")
    p.add_argument("--window", type=int, default=10, help="predictive: seconds used to compute the trend")
    p.add_argument("--horizon", type=int, default=10, help="predictive: how many seconds ahead to predict")
    p.add_argument("--cooldown", type=int, default=30, help="seconds to wait after a transfer")
    args = p.parse_args()

    os.makedirs(args.out, exist_ok=True)
    probes_file = open(os.path.join(args.out, "probes.csv"), "w", newline="")
    actions_file = open(os.path.join(args.out, "actions.csv"), "w", newline="")
    probes = csv.writer(probes_file)
    actions = csv.writer(actions_file)
    probes.writerow(["timestamp", "node", "rtt_ms", "is_leader"])
    actions.writerow(["timestamp", "action", "from", "to", "detail"])

    history = {name: [] for name in NODES} # recent response times of every node
    calibration = [] # leader response times in the first seconds
    threshold = None
    slow_count = 0
    alarm_count = 0
    last_transfer = 0.0
    start = time.time()

    while time.time() - start < args.duration:
        tick = time.time()
        leader, ids, rtts = poll_nodes()
        for name, rtt in rtts.items():
            history[name] = (history[name] + [rtt])[-60:]
            probes.writerow([f"{tick:.3f}", name, f"{rtt:.2f}", int(name == leader)])
        probes_file.flush()

        if leader is not None:
            current = statistics.median(history[leader][-3:])
            if threshold is None:
                calibration.append(current)
                if tick - start >= args.calibration:
                    normal = statistics.median(calibration)
                    threshold = max(args.factor * normal, normal + args.min_margin)
                    actions.writerow([f"{tick:.3f}", "calibrated", leader, "", f"normal={normal:.2f}ms threshold={threshold:.2f}ms"])
            elif args.mode != "none" and tick - last_transfer > args.cooldown:
                decide = False
                if args.mode == "reactive":
                    slow_count = slow_count + 1 if current > threshold else 0
                    decide = slow_count >= args.reactive_seconds
                    detail = f"slow for {slow_count}s, current={current:.1f}ms"
                else:
                    h = history[leader]
                    smooth = [statistics.median(h[max(0, i - 2):i + 1]) for i in range(len(h))]
                    recent = smooth[-args.window:]
                    if len(recent) == args.window:
                        predicted = statistics.mean(recent[-3:]) + slope(recent) * args.horizon
                        alarm_count = alarm_count + 1 if predicted > threshold else 0
                        decide = alarm_count >= 2
                        detail = f"predicted={predicted:.1f}ms, current={current:.1f}ms"
                if decide:
                    others = [n for n in NODES if n != leader and n in ids]
                    target = min(others, key=lambda n: statistics.median(history[n][-5:]))
                    ok = transfer_leadership(leader, target, ids)
                    actions.writerow([f"{time.time():.3f}", "transfer" if ok else "transfer_failed", leader, target, detail])
                    last_transfer = time.time()
                    slow_count = alarm_count = 0
                    history[leader] = []
            actions_file.flush()

        time.sleep(max(0.0, 1.0 - (time.time() - tick)))

    probes_file.close()
    actions_file.close()


if __name__ == "__main__":
    main()