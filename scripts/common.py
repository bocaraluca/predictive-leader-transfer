"""Helpers shared by the other scripts: node addresses, etcd status, leader transfer"""

import time
import requests

# Node name -> address of the node on the laptop (ports in docker-compose.yml)
NODES = {
    "etcd1": "http://localhost:2379",
    "etcd2": "http://localhost:22379",
    "etcd3": "http://localhost:32379",
}


def get_status(url, timeout=2.0):
    """Ask one node for its status. Returns (member_id, leader_id, response_time_ms)
    If the node does not answer in time, returns (None, None, timeout in ms)"""
    t0 = time.perf_counter()
    try:
        r = requests.post(url + "/v3/maintenance/status", json={}, timeout=timeout)
        data = r.json()
        rtt = (time.perf_counter() - t0) * 1000
        return data["header"]["member_id"], data["leader"], rtt
    except (requests.RequestException, ValueError, KeyError):
        return None, None, timeout * 1000


def poll_nodes():
    """Asks every node for its status once
    Returns (leader_name, {name: member_id}, {name: response_time_ms})"""
    ids, rtts = {}, {}
    leader_id = None
    for name, url in NODES.items():
        member_id, leader, rtt = get_status(url)
        rtts[name] = rtt
        if member_id is not None:
            ids[name] = member_id
            leader_id = leader_id or leader
    leader_name = next((n for n, i in ids.items() if i == leader_id), None)
    return leader_name, ids, rtts


def find_leader():
    """Returns (leader_name, {name: member_id})"""
    leader_name, ids, _ = poll_nodes()
    return leader_name, ids


def transfer_leadership(leader_name, target_name, ids):
    """Asks the current leader to hand leadership to target_name (etcd 'move-leader')"""
    url = NODES[leader_name] + "/v3/maintenance/transfer-leadership"
    r = requests.post(url, json={"targetID": ids[target_name]}, timeout=5)
    return r.status_code == 200 and "error" not in r.json()