# ESI DC Network Project

This repository contains a lightweight Arista EOS data center fabric deployment and management lab built around Ansible templates, inventory definitions, and a small Flask-based topology dashboard.

## Overview

The project is designed to:

- provision a spine-and-leaf EOS fabric using Ansible
- manage device configuration through Jinja2 templates
- model a simple topological lab with a Flask app
- collect device status and config output over SSH

It includes:

- Ansible inventory in `inventory.ini`
- Group variables shared across devices in `group_vars/`
- Host-specific variables in `host_vars/`
- EOS configuration templates in `templates/`
- A deployment playbook in `deploy_dc_fabric.yml`
- A Flask app in `app.py` for topology/status visualization

## Repository Structure

```text
.
├── app.py                    # Flask app for topology/status UI and SSH checks
├── deploy_dc_fabric.yml      # Ansible playbook for EOS config deployment
├── index.html                # Frontend template used by the Flask app
├── inventory.ini             # Inventory with leaf and spine definitions
├── group_vars/
│   └── all.yml              # Shared fabric settings and VLAN definitions
├── host_vars/
│   ├── leaf1.yml
│   ├── leaf2.yml
│   ├── leaf3.yml
│   ├── spine1.yml
│   └── spine2.yml
├── templates/
│   ├── eos_fabric.j2        # Shared EOS template used by the fabric
│   ├── eos_leaf.j2          # Leaf-specific rendering
│   └── eos_spine.j2         # Spine-specific rendering
└── README.md
```

## Prerequisites

Before using the project, make sure you have:

- Python 3
- Ansible installed
- The `arista.eos` Ansible collection installed
- Access to the target EOS devices in your lab or EVE-NG environment
- SSH access enabled on the Arista switches
- The correct management IPs and credentials configured in the inventory and variables

Install the required collection if needed:

```bash
ansible-galaxy collection install arista.eos
```

## Configuration

### Inventory

Edit `inventory.ini` to match your lab topology. The file currently defines:

- 3 leaves: `leaf1`, `leaf2`, `leaf3`
- 2 spines: `spine1`, `spine2`

Each host is assigned an `ansible_host` value and the related Ansible variables for EOS connection.

### Group Variables

The shared values in `group_vars/all.yml` include:

- management VRF settings
- VLAN definitions and VNI mappings
- MTU and VXLAN parameters
- EVPN/BGP-related parameters

### Host Variables

The files under `host_vars/` contain per-device settings such as:

- hostnames
- loopback addresses
- BGP ASN and router IDs
- uplink and host-port definitions

Update these to match your actual fabric design.

## Deployment

Run the Ansible playbook from the project root:

```bash
ansible-playbook -i inventory.ini deploy_dc_fabric.yml
```

This playbook:

1. selects the correct EOS template based on the device role
2. renders the configuration from Jinja2
3. pushes it to the device using `arista.eos.eos_config`
4. collects the device version output for validation

## Flask App

The app in `app.py` can be used to inspect the topology and run common EOS show commands remotely via SSH.

Start it with:

```bash
python app.py
```

Then open the application in a browser, typically at:

```text
http://localhost:5000
```

The app exposes endpoints such as:

- `/` for the topology dashboard
- `/api/topology` for topology data
- `/api/status` for node reachability
- `/api/node/<node_name>/running-config` for full config retrieval
- `/api/node/<node_name>/command/<command_name>` for common operational commands

## Notes

- This project is intended for lab or demonstration environments.
- The IPs and credentials in the example files should be replaced with your environment-specific values.
- The Flask app assumes SSH credentials match the Ansible inventory settings.
- The topology and link definitions may need adjustment if your lab network differs from the default example.

## Example Use Cases

- Deploy a basic EVPN/VXLAN leaf-spine fabric
- Validate BGP adjacency and VLAN/VNI mapping
- Test automation templates before production rollout
- Use the Flask app as a simple network lab dashboard

## License

This project is provided as-is for educational and lab use.
