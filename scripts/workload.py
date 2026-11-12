import argparse
import base64
import csv
import os
import statistics
import time
import requests

def b64(text):
    return base64.b64encode(text.encode()).decode()


def main():
    parser = argparse.ArgumentParser(description="Send writes to etcd and record the latency of each one")
    parser.add_argument("--endpoints", default="http://localhost:2379,http://localhost:22379,http://localhost:32379")
    parser.add_argument("--duration", type=float, default=30, help="how many seconds to run")
    parser.add_argument("--interval", type=float, default=0.05, help="pause between writes, in seconds")
    parser.add_argument("--out", default="results/workload.csv")
    args = parser.parse_args()

    endpoints = args.endpoints.split(",")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    session = requests.Session()
    latencies = []
    start = time.time()
    i = 0

    with open(args.out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "endpoint", "latency_ms", "ok"])
        while time.time() - start < args.duration:
            endpoint = endpoints[i % len(endpoints)]
            body = {"key": b64(f"key{i % 1000}"), "value": b64("x" * 100)}
            t0 = time.perf_counter()
            try:
                response = session.post(endpoint + "/v3/kv/put", json=body, timeout=5)
                ok = response.status_code == 200
            except requests.RequestException:
                ok = False
            latency = (time.perf_counter() - t0) * 1000
            writer.writerow([f"{time.time():.3f}", endpoint, f"{latency:.2f}", int(ok)])
            if ok:
                latencies.append(latency)
            i += 1
            time.sleep(args.interval)

    latencies.sort()
    if latencies:
        p99 = latencies[int(0.99 * (len(latencies) - 1))]
        print(f"{i} writes, {len(latencies)} ok")
        print(f"median: {statistics.median(latencies):.2f} ms, p99: {p99:.2f} ms")
    print(f"saved to {args.out}")


if __name__ == "__main__":
    main()