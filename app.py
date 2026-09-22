from flask import Flask, jsonify, render_template
import paramiko
import configparser
import os
from datetime import datetime

app = Flask(__name__)

# Inventory parsing

INVENTORY_PATH = os.path.join(os.path.dirname(__file__), "inventory.ini")


def parse_inventory(path: str) -> dict:
    """
    Parse an Ansible-style inventory.ini and return:
      {
        "hosts": ["10.x.x.x", ...],
        "vars": {"ansible_user": ..., "ansible_password": ..., ...}
      }
    """
    config = configparser.ConfigParser(allow_no_value=True)
    config.optionxform = str.lower

    with open(path) as fh:
        raw = fh.read()

    # Only prepend a section header if the file doesn't already have one,
    # so bare IP lines at the top are still captured without duplicating.
    if not raw.lstrip().startswith("["):
        raw = "[switches]\n" + raw

    config.read_string(raw)

    hosts = []
    group_vars = {}

    for section in config.sections():
        if section.endswith(":vars"):
            for key, val in config.items(section):
                group_vars[key] = val
        else:
            for key, val in config.items(section):
                # bare host lines: key = ip, val = None
                if val is None:
                    hosts.append(key)
                elif "=" not in key:
                    hosts.append(key)

    # Deduplicate while preserving order
    seen = set()
    unique_hosts = []
    for h in hosts:
        if h not in seen:
            seen.add(h)
            unique_hosts.append(h)

    return {"hosts": unique_hosts, "vars": group_vars}


INVENTORY = parse_inventory(INVENTORY_PATH)

SSH_USER = INVENTORY["vars"].get("ansible_user", "admin")
SSH_PASS = INVENTORY["vars"].get("ansible_password", "")
SSH_PORT = int(INVENTORY["vars"].get("ansible_port", 22))

# Node name mapping: first 2 hosts = spines, remaining = leaves
_NODE_NAMES = [
    ("leaf1",  "Leaf 1",  "leaf"),
    ("leaf2",  "Leaf 2",  "leaf"),
    ("leaf3",  "Leaf 3",  "leaf"),
    ("spine1", "Spine 1", "spine"),
    ("spine2", "Spine 2", "spine"),
]

NODES: dict = {}
for idx, ip in enumerate(INVENTORY["hosts"]):
    if idx < len(_NODE_NAMES):
        node_id, label, role = _NODE_NAMES[idx]
    else:
        node_id = f"switch{idx + 1}"
        label   = f"Switch {idx + 1}"
        role    = "switch"
    NODES[node_id] = {"label": label, "role": role, "mgmt_ip": ip}

# Static link topology -- edit to match your EVE-NG lab cabling
LINKS: list = [
    # Example: {"a": "switch1", "b": "switch2", "a_if": "Gi0/1", "b_if": "Gi0/0"},
]

LAB_NAME = "eve-ng-lab"


# SSH helpers

def ssh_command(host: str, command: str, timeout: int = 20) -> dict:
    """Run a single IOS command over SSH and return a result dict."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            port=SSH_PORT,
            username=SSH_USER,
            password=SSH_PASS,
            timeout=timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        rc = stdout.channel.recv_exit_status()
        client.close()
        return {"ok": rc == 0 or out.strip() != "", "returncode": rc,
                "stdout": out, "stderr": err, "cmd": command}
    except Exception as exc:
        return {"ok": False, "returncode": 1, "stdout": "",
                "stderr": str(exc), "cmd": command}


def node_ssh_command(node_name: str, command: str, timeout: int = 20) -> dict:
    node = NODES.get(node_name)
    if not node:
        return {"ok": False, "error": f"Unknown node: {node_name}",
                "stdout": "", "stderr": ""}
    return ssh_command(node["mgmt_ip"], command, timeout=timeout)


def check_reachable(host: str, timeout: int = 6) -> tuple:
    """Quick SSH connect check; returns (reachable, status_string)."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            port=SSH_PORT,
            username=SSH_USER,
            password=SSH_PASS,
            timeout=timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        client.close()
        return True, "running"
    except Exception as exc:
        return False, str(exc)[:80]


# Routes

@app.route("/")
def index():
    return render_template("index.html", nodes=NODES, links=LINKS, lab_name=LAB_NAME)


@app.route("/api/topology")
def topology():
    return jsonify({
        "ok": True,
        "lab_name": LAB_NAME,
        "nodes": NODES,
        "links": LINKS,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    })


@app.route("/api/node/<node_name>/running-config")
def running_config(node_name: str):
    result = node_ssh_command(node_name, "show running-config", timeout=30)
    if not result.get("ok"):
        return jsonify({
            "ok": False,
            "node": node_name,
            "error": result.get("stderr") or result.get("stdout") or "Failed to get running config",
            "cmd": result.get("cmd"),
        }), 500

    return jsonify({
        "ok": True,
        "node": node_name,
        "mgmt_ip": NODES[node_name]["mgmt_ip"],
        "command": "show running-config",
        "output": result["stdout"],
        "timestamp": datetime.utcnow().isoformat() + "Z",
    })


@app.route("/api/node/<node_name>/command/<command_name>")
def node_command_route(node_name: str, command_name: str):
    allowed_commands = {
        "interfaces": "show ip interface brief",
        "bgp":        "show ip bgp summary",
        "routes":     "show ip route",
        "lldp":       "show lldp neighbors",
        "version":    "show version",
        "cdp":        "show cdp neighbors detail",
        "arp":        "show arp",
        "mac":        "show mac address-table",
        "ospf":       "show ip ospf neighbor",
        "vlan":       "show vlan brief",
        "vrf":        "show vrf",
    }

    if command_name not in allowed_commands:
        return jsonify({
            "ok": False,
            "error": f"Command not allowed: {command_name}",
            "allowed": list(allowed_commands.keys()),
        }), 400

    command = allowed_commands[command_name]
    result = node_ssh_command(node_name, command, timeout=20)

    if not result.get("ok"):
        return jsonify({
            "ok": False,
            "node": node_name,
            "command": command,
            "error": result.get("stderr") or result.get("stdout") or "Command failed",
            "cmd": result.get("cmd"),
        }), 500

    return jsonify({
        "ok": True,
        "node": node_name,
        "mgmt_ip": NODES[node_name]["mgmt_ip"],
        "command": command,
        "output": result["stdout"],
        "timestamp": datetime.utcnow().isoformat() + "Z",
    })


@app.route("/api/status")
def status():
    status_data = {}
    for node_name, node in NODES.items():
        reachable, ssh_status = check_reachable(node["mgmt_ip"])
        status_data[node_name] = {
            "label": node["label"],
            "mgmt_ip": node["mgmt_ip"],
            "role": node["role"],
            "running": reachable,
            "ssh_status": ssh_status,
        }

    return jsonify({
        "ok": True,
        "lab_name": LAB_NAME,
        "nodes": status_data,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
