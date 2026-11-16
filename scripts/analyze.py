"""Computes the results of all runs of one scenario and draws the latency graph

Example:
  python scripts/analyze.py --scenario net-gradual
"""
import argparse
import glob
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def analyze_run(folder):
    meta = json.load(open(os.path.join(folder, "meta.json")))
    w = pd.read_csv(os.path.join(folder, "workload.csv"))
    w = w[w["ok"] == 1]
    w["t"] = w["timestamp"] - meta["degradation_start"] # seconds since the slowdown started

    normal = w[w["t"] < 0]["latency_ms"].median()
    during = w[w["t"] >= 0]["latency_ms"]

    per_second = w[w["t"] >= 0].groupby(w["t"].astype(int))["latency_ms"].median()
    slow_seconds = int((per_second > 2 * normal).sum())

    actions = pd.read_csv(os.path.join(folder, "actions.csv"))
    transfers = actions[actions["action"] == "transfer"]
    first = transfers["timestamp"].min() - meta["degradation_start"] if len(transfers) else None

    return {
        "run": os.path.basename(folder),
        "mode": meta["mode"],
        "rep": meta["rep"],
        "normal_median_ms": round(normal, 1),
        "median_ms": round(during.median(), 1),
        "p99_ms": round(during.quantile(0.99), 1),
        "slow_seconds": slow_seconds,
        "transfers": len(transfers),
        "first_transfer_s": None if first is None else round(first, 1),
    }, w, transfers["timestamp"] - meta["degradation_start"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", required=True)
    p.add_argument("--plot-rep", type=int, default=1)
    args = p.parse_args()
    base = os.path.join("results", args.scenario)

    rows, curves = [], {}
    for folder in sorted(glob.glob(os.path.join(base, "*_rep*"))):
        if not os.path.exists(os.path.join(folder, "meta.json")):
            continue
        row, w, transfer_times = analyze_run(folder)
        rows.append(row)
        if row["rep"] == args.plot_rep:
            curves[row["mode"]] = (w, transfer_times)

    summary = pd.DataFrame(rows)
    summary.to_csv(os.path.join(base, "summary.csv"), index=False)
    print(summary.to_string(index=False))
    print("\nAverage per mode:")
    print(summary.groupby("mode")[["median_ms", "p99_ms", "slow_seconds", "transfers", "first_transfer_s"]].mean().round(1))

    plt.figure(figsize=(9, 4.5))
    for mode, (w, transfer_times) in sorted(curves.items()):
        line = w.groupby(w["t"].astype(int))["latency_ms"].median()
        plotted = plt.plot(line.index, line.values, label=mode)
        for t in transfer_times:
            plt.axvline(t, color=plotted[0].get_color(), linestyle="--", alpha=0.7)
    plt.axvline(0, color="gray", linestyle=":", label="degradation starts")
    plt.xlabel("time since degradation started (s)")
    plt.ylabel("write latency, median per second (ms)")
    plt.title(f"Scenario: {args.scenario} (dashed lines = leader transfers)")
    plt.legend()
    plt.tight_layout()
    name = f"latency_rep{args.plot_rep}.png"
    plt.savefig(os.path.join(base, name), dpi=150)
    print(f"\nGraph saved to {os.path.join(base, name)}")


if __name__ == "__main__":
    main()