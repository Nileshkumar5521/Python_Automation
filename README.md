# Python_Automation
# Network MAC Scanner

A multi-threaded Python tool to scan network devices (Huawei and Alcatel AOS) over SSH and locate a specific MAC address quickly.

---

## Table of Contents

1. [Overview](#overview)
2. [Key Features](#key-features)
3. [Prerequisites](#prerequisites)
4. [Installation](#installation)
5. [Configuration & Credentials](#configuration--credentials)
6. [Device File Format](#device-file-format)
7. [Usage / Examples](#usage--examples)
8. [Sample Output](#sample-output)
9. [How It Works (Internals)](#how-it-works-internals)
10. [Advanced Options & Tuning](#advanced-options--tuning)
11. [Logging & Debugging](#logging--debugging)
12. [Troubleshooting / FAQ](#troubleshooting--faq)
13. [Security Considerations](#security-considerations)
14. [Testing Locally](#testing-locally)
15. [Contributing](#contributing)
16. [License](#license)

---

## Overview

`network-mac-scanner` is a command-line utility written in Python that connects to a list of network devices (currently supports Huawei and Alcatel AOS), issues vendor-specific commands to search the device MAC forwarding tables, and reports where a given MAC address is learned (interface, VLAN/service, timestamp or type). The tool is designed to:

* Scan devices in parallel using a thread pool.
* Stop the scan early once the MAC is found (to save time).
* Provide progress and ETA information.

Use cases: locating devices on large networks, automating trouble-ticket workflows, and quickly mapping where a client is connected.

---

## Key Features

* Multi-threaded scanning with configurable concurrency
* Huawei and Alcatel AOS parsing rules implemented
* Fast socket-level check before attempting SSH
* Environment-variable credential support for safer usage
* Progress / ETA display
* Clean, human-readable output and exit codes

---

## Prerequisites

* Python 3.8+ (3.10 recommended)
* `netmiko` Python library for SSH device connections
* Network access (SSH/TCP port 22) from the host running the script to the target devices

---

## Installation

1. Clone this repository (or copy the files into a directory):

```bash
git clone https://github.com/yourusername/network-mac-scanner.git
cd network-mac-scanner
```

2. Create and activate a virtual environment (recommended):

```bash
python -m venv .venv
source .venv/bin/activate   # Linux / macOS
.\.venv\Scripts\activate  # Windows (PowerShell)
```

3. Install requirements:

```bash
pip install -r requirements.txt
```

`requirements.txt` should contain at least:

```
netmiko>=4.3.0
```

---

## Configuration & Credentials

For security, do **not** hardcode credentials in the script. Use environment variables instead.

* `NETSCAN_USER` — SSH username
* `NETSCAN_PASS` — SSH password

Export them in your shell before running:

```bash
export NETSCAN_USER=myuser
export NETSCAN_PASS=mypassword
```

On Windows (PowerShell):

```powershell
$env:NETSCAN_USER = 'myuser'
$env:NETSCAN_PASS = 'mypassword'
```

You may also integrate this project with a secrets manager (HashiCorp Vault, AWS Secrets Manager, etc.) in your automation pipeline.

---

## Device File Format

The script reads a plain text `devices.txt` file where each line represents a device. The format is CSV with two fields: `IP, vendor`.

Supported `vendor` values (case-insensitive):

* `huawei` — for Huawei devices
* `alcatel_aos` — for Alcatel AOS devices

Example `devices.txt`:

```
192.168.1.10,huawei
192.168.1.11,huawei
10.0.0.20,alcatel_aos
10.0.0.21,alcatel_aos
```

Rules:

* Lines with missing/invalid vendor will be skipped.
* Blank lines are ignored.
* Leading/trailing spaces are trimmed.

---

## Usage / Examples

Basic usage:

```bash
python src/mac_scanner.py devices.txt AA:BB:CC:DD:EE:FF
```

This will:

* Spawn a thread pool (default concurrency is 40; you can tune it in the script),
* Attempt a quick TCP connect to port 22 for each device before doing SSH,
* Run the appropriate vendor command to search the MAC forwarding table,
* Stop scanning when the MAC is found and print a summary.

### Example: running with environment variables

```bash
export NETSCAN_USER=netops
export NETSCAN_PASS=SuperS3cret
python src/mac_scanner.py devices.txt aa:bb:cc:dd:ee:ff
```

### Notes on MAC format

* You can pass MAC in any common delimiter format: `AA:BB:CC:DD:EE:FF`, `AA-BB-CC-DD-EE-FF`, or `AABBCCDDEEFF`.
* The script normalizes the value for each vendor command (Huawei expects `xxxx-xxxx-xxxx`, Alcatel expects standard `aa:bb:cc:dd:ee:ff` match patterns).

---

## Sample Output

```
[DEBUG] Total devices to scan: 4
[PROGRESS] 2/4 devices scanned | ETA: 00:00:05

========== SCAN SUMMARY ==========
[+] MAC AA:BB:CC:DD:EE:FF found on device switch1.example.com (192.168.1.10)
    • Interface: 1/0/24
    • VLAN/VSI=10
    • Type=Dynamic
==================================
```

If not found:

```
[!] MAC AA:BB:CC:DD:EE:FF not found on any device.
```

---

## How It Works (Internals)

1. **Connection pre-check**: the script opens a TCP socket to port 22 to quickly determine whether SSH is reachable. If port 22 is closed, it avoids waiting on a long SSH timeout.

2. **Netmiko SSH**: when the TCP check succeeds, `ConnectHandler` from Netmiko establishes an SSH session.

3. **Per-vendor commands**:

   * **Huawei**: `display mac-address | include <huawei-formatted-mac>`
   * **Alcatel AOS**: `show service fdb-mac | match <mac>`

4. **Parsing**: Each vendor has regex parsing tailored to the command output to extract MAC, interface, VLAN/service, timestamp or type.

5. **Early exit**: A global `threading.Event` is set when the MAC is found, which prompts all threads to exit gracefully.

---

## Advanced Options & Tuning

* **Concurrency**: change `max_workers` in the script to increase/decrease parallelism. For large device counts and a capable scanning host, you can scale up — but monitor resource usage.

* **Per-device timeout**: tune `timeout_per_device` for slower devices or congested networks.

* **Global delays**: the `ConnectHandler` uses `global_delay_factor` — increase it if you see rate-limited or slow SSH responses.

* **Logging**: integrate Python logging to write to a file instead of console for audits. Add rotating file handler for long-running scans.

---

## Logging & Debugging

The script outputs debug messages with bracket prefixes like `[DEBUG]`, `[X]`, `[!]`, and `[PROGRESS]`.

To enable more detailed logging (recommended for debugging), replace `print()` statements with the standard `logging` module and set a logging level via environment variable or CLI flag.

Example snippet to add at the top of the script:

```python
import logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
LOG = logging.getLogger(__name__)
```

Then use `LOG.debug(...)`, `LOG.info(...)`, `LOG.warning(...)`, `LOG.error(...)`.

---

## Troubleshooting / FAQ

**Q: Script hangs on a device for a long time.**

* A: Check network reachability and SSH port. The script does a TCP connect pre-check — if that succeeds but Netmiko hangs, increase `timeout` or `global_delay_factor`.

**Q: Netmiko authentication failure.**

* A: Ensure `NETSCAN_USER` / `NETSCAN_PASS` are correct and that the account has permission to run the vendor command.

**Q: The vendor output format differs and parsing fails.**

* A: Device OS versions often change output formatting. Inspect the raw command output by temporarily capturing `mac_output` to a file and adjust the regex in the corresponding handler.

**Q: I want to scan devices requiring SSH key auth.**

* A: Modify `device` dictionary to include `use_keys=True` and point to `key_file`. Netmiko supports SSH key auth; you can also use an SSH agent.

---

## Security Considerations

* Avoid storing plaintext credentials in the repo.
* Run scans from a trusted host inside your network (VPN or management VLAN).
* Consider service accounts with least privileges required to execute the show commands.
* Store credentials in a secrets manager if integrating with automation.

---

## Testing Locally

To test without touching production devices, create a small lab with mock devices or use `ssh` servers that echo expected command outputs, then adjust the handlers to accept the mocked output.

You may also create unit tests for the parsing regex using `pytest`.

Example `pytest` case for Huawei parsing:

```python
from src.mac_scanner import handle_huawei_device

sample_output = """
0011-2233-4455 10  GigabitEthernet1/0/24 dynamic
"""
# write wrapper around handler or unit test the parsing regex directly
```

---

## Contributing

Contributions are welcome! Suggested workflow:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/some-change`)
3. Add tests for new parsing logic or features
4. Submit a pull request with a clear description

Please follow repository coding style and add tests for parsing logic.

---

## License

This project is provided under the MIT License. See the `LICENSE` file for details.

---

## Contact

If you have questions, feature requests, or run into parsing issues with a device/OS version, open an issue on GitHub with the device model and a redacted example of the command output.
