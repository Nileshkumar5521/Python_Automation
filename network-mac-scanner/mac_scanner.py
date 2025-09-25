#!/usr/bin/env python3
"""
Network MAC Address Scanner
---------------------------
This tool scans Huawei and Alcatel devices via SSH to find the given MAC address.

Author: Your Name
License: MIT
"""

import sys
import os
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from netmiko import ConnectHandler

# ---------- Progress Tracking ----------
progress_lock = threading.Lock()
total_devices = 0
completed_devices = 0
scan_start_time = None

# ---------- Shared Stop Flag ----------
mac_found_event = threading.Event()

# ---------- Credentials (set via env vars for security) ----------
USERNAME = os.getenv("NETSCAN_USER", "")
PASSWORD = os.getenv("NETSCAN_PASS", "")


def ssh_connect(device):
    """Try to establish SSH connection to a device."""
    try:
        print(f"[DEBUG] Trying to connect to {device['host']}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15)
        sock.connect((device['host'], 22))
        sock.close()
        print(f"[DEBUG] Socket connection successful to {device['host']}")
        return ConnectHandler(
            **device,
            timeout=60,
            global_delay_factor=5
        )
    except Exception as e:
        print(f"[X] Connection error for {device['host']}: {e}")
        return None


def mac_to_huawei_format(mac):
    """Convert standard MAC to Huawei xxxx-xxxx-xxxx format."""
    mac_clean = re.sub(r"[^0-9a-fA-F]", "", mac)
    return f"{mac_clean[0:4]}-{mac_clean[4:8]}-{mac_clean[8:12]}"


def huawei_mac_to_standard(mac):
    """Convert Huawei format xxxx-xxxx-xxxx back to standard AA:BB:CC:DD:EE:FF."""
    mac_clean = mac.replace("-", "").lower()
    return ":".join(mac_clean[i:i+2] for i in range(0, 12, 2)).upper()


def handle_huawei_device(conn, hostname, ip, search_mac, timeout=60):
    """Check Huawei device for MAC address."""
    if mac_found_event.is_set():
        return None

    huawei_mac = mac_to_huawei_format(search_mac).lower()
    cmd = f"display mac-address | include {huawei_mac}"
    print(f"[DEBUG] Sending command to Huawei device {hostname}: {cmd}")

    conn.send_command("screen-length 0 temporary")
    start_time = time.time()

    while time.time() - start_time < timeout:
        if mac_found_event.is_set():
            return None

        mac_output = conn.send_command_timing(cmd, delay_factor=2).strip()
        if not mac_output:
            print(f"[DEBUG] No output from {hostname}, skipping wait")
            return None

        if huawei_mac in mac_output.lower():
            break

        time.sleep(2)

    if huawei_mac not in mac_output.lower():
        print(f"[!] MAC {search_mac} not found on {hostname}")
        return None

    pattern = re.compile(
        r"(?P<mac>[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4})\s+"
        r"(?P<vlan>\S+)\s+"
        r"(?P<interface>\S+)\s+"
        r"(?P<type>\S+)",
        re.IGNORECASE
    )

    for line in mac_output.splitlines():
        match = pattern.search(line)
        if match:
            mac_huawei = match.group("mac").upper()
            mac = huawei_mac_to_standard(mac_huawei)
            vlan = match.group("vlan")
            interface = match.group("interface")
            mac_type = match.group("type")
            print(f"[DEBUG] Parsed -> MAC={mac}, VLAN/VSI={vlan}, Interface={interface}, Type={mac_type}")
            mac_found_event.set()
            return mac, interface, ip, hostname, f"VLAN/VSI={vlan}", f"Type={mac_type}"

    return None


def handle_alcatel_device(conn, hostname, ip, search_mac, timeout=60):
    """Check Alcatel device for MAC address."""
    if mac_found_event.is_set():
        return None

    search_mac_lower = search_mac.lower()
    cmd = f"show service fdb-mac | match {search_mac_lower}"
    print(f"[DEBUG] Sending command to Alcatel device {hostname}: {cmd}")

    conn.send_command("environment no more")
    start_time = time.time()

    while time.time() - start_time < timeout:
        if mac_found_event.is_set():
            return None

        mac_output = conn.send_command_timing(cmd, delay_factor=2).strip()
        if not mac_output:
            print(f"[DEBUG] No output from {hostname}, skipping wait")
            return None

        if search_mac_lower in mac_output.lower():
            break

        time.sleep(2)

    if search_mac_lower not in mac_output.lower():
        print(f"[!] MAC {search_mac} not found on {hostname}")
        return None

    pattern = re.compile(
        r"(?P<service>\d+)\s+"
        r"(?P<mac>([0-9a-f]{2}[:\-]){5}[0-9a-f]{2})\s+sap:(?P<interface>[\w\-:]+)\s+"
        r"(?P<age>[LD]/\d+)\s+"
        r"(?P<timestamp>\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})",
        re.IGNORECASE
    )

    for line in mac_output.splitlines():
        match = pattern.search(line)
        if match:
            service = match.group("service")
            mac = match.group("mac").replace("-", ":").upper()
            interface = match.group("interface")
            timestamp = match.group("timestamp")
            print(f"[DEBUG] Parsed -> Service={service}, MAC={mac}, Interface={interface}, LastSeen={timestamp}")
            mac_found_event.set()
            return mac, interface, ip, hostname, f"Service={service}", f"LastSeen={timestamp}"

    return None


def handle_device(device_info, search_mac, timeout=60):
    """Handle scanning of a single device."""
    global completed_devices, scan_start_time

    if mac_found_event.is_set():
        return None

    parts = device_info.strip().split(",")
    if len(parts) != 2:
        with progress_lock:
            completed_devices += 1
            print_progress()
        return None

    ip, vendor = parts[0].strip(), parts[1].strip().lower()
    if vendor not in ["huawei", "alcatel_aos"]:
        with progress_lock:
            completed_devices += 1
            print_progress()
        return None

    device = {
        'device_type': vendor,
        'host': ip,
        'username': USERNAME,
        'password': PASSWORD,
    }

    try:
        conn = ssh_connect(device)
        if not conn:
            return None

        conn.set_base_prompt()
        hostname = conn.find_prompt().strip('<># ').strip()

        if vendor == "huawei":
            result = handle_huawei_device(conn, hostname, ip, search_mac, timeout)
        else:
            result = handle_alcatel_device(conn, hostname, ip, search_mac, timeout)

        conn.disconnect()
        return result
    except Exception as e:
        print(f"[X] Error on {ip}: {e}")
        return None
    finally:
        with progress_lock:
            completed_devices += 1
            print_progress()


def print_progress():
    """Display scanning progress with ETA."""
    global completed_devices, total_devices, scan_start_time

    if scan_start_time is None:
        return

    elapsed = time.time() - scan_start_time
    avg_time_per_device = elapsed / completed_devices if completed_devices > 0 else 0
    remaining_devices = total_devices - completed_devices
    eta_seconds = avg_time_per_device * remaining_devices
    eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_seconds))

    print(f"[PROGRESS] {completed_devices}/{total_devices} devices scanned | ETA: {eta_str}", end="\r")


def main():
    global total_devices, scan_start_time
    if len(sys.argv) != 3:
        print("Usage: python mac_scanner.py <device_file> <mac_to_search>")
        sys.exit(1)

    device_file = sys.argv[1]
    search_mac = sys.argv[2].lower()

    try:
        with open(device_file, "r") as f:
            devices = f.readlines()
    except FileNotFoundError:
        print(f"[!] File {device_file} not found.")
        sys.exit(1)

    total_devices = len(devices)
    print(f"[DEBUG] Total devices to scan: {total_devices}")

    scan_start_time = time.time()
    max_workers = 40
    found_result = None
    timeout_per_device = 60

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_device = {executor.submit(handle_device, device_info, search_mac, timeout_per_device): device_info for device_info in devices}

        for future in as_completed(future_to_device):
            if mac_found_event.is_set() and found_result:
                break

            try:
                result = future.result()
                if result:
                    found_result = result
                    mac_found_event.set()
                    break
            except Exception as e:
                device_info = future_to_device[future]
                print(f"[X] Error scanning device {device_info.strip()}: {e}")

        if found_result:
            for fut in future_to_device:
                if not fut.done():
                    fut.cancel()

    print("\n========== SCAN SUMMARY ==========")
    if found_result:
        print(f"[+] MAC {found_result[0]} found on device {found_result[3]} ({found_result[2]})")
        print(f"    • Interface: {found_result[1]}")
        print(f"    • {found_result[4]}")
        print(f"    • {found_result[5]}")
    else:
        print(f"[!] MAC {search_mac.upper()} not found on any device.")
    print("==================================\n")


if __name__ == "__main__":
    main()
