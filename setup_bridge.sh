#!/bin/bash
# Bridge eth1 (USB-to-LAN) to eth0 on Raspberry Pi 4
# This allows network traffic to flow between the two interfaces

set -e

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

echo "Setting up bridge between eth0 and eth1..."

# Install bridge-utils if not present
if ! command -v brctl &> /dev/null; then
    echo "Installing bridge-utils..."
    apt-get update
    apt-get install -y bridge-utils
fi

# Stop networking temporarily
echo "Configuring bridge interface..."

# Create bridge interface
brctl addbr br0

# Add both ethernet interfaces to the bridge
brctl addif br0 eth0
brctl addif br0 eth1

# Bring interfaces up
ip link set dev eth0 up
ip link set dev eth1 up
ip link set dev br0 up

# Enable IP forwarding
echo "Enabling IP forwarding..."
sysctl -w net.ipv4.ip_forward=1

# Flush any existing IPs from eth0 and eth1
echo "Removing IPs from eth0 and eth1..."
ip addr flush dev eth0 2>/dev/null || true
ip addr flush dev eth1 2>/dev/null || true

# Assign static IP to bridge (192.168.10.1/24 for camera network)
echo "Assigning 192.168.10.1/24 to br0..."
ip addr add 192.168.10.1/24 dev br0

echo ""
echo "Bridge setup complete!"
echo "Bridge interface br0 created with eth0 and eth1"
echo ""
echo "Current bridge status:"
brctl show

echo ""
echo "To make this persistent across reboots, run:"
echo "    sudo ./setup_bridge_persistent.sh"
echo ""
echo "Or manually add to /etc/network/interfaces:"
echo ""
echo "auto br0"
echo "iface br0 inet static"
echo "    address 192.168.10.1"
echo "    netmask 255.255.255.0"
echo "    bridge_ports eth0 eth1"
echo "    bridge_stp off"
echo "    bridge_fd 0"
