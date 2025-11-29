#!/bin/bash
# Automatically switch Realtek USB adapter from CD-ROM to Ethernet mode
# and add to bridge

set -e

echo "Checking for Realtek USB Ethernet adapter..."

# Wait for USB to settle
sleep 2

# Check if device is in CD-ROM mode
if lsusb | grep -q "0bda:8151"; then
    echo "Found Realtek RTL8151 adapter"
    
    # Install usb-modeswitch if needed
    if ! command -v usb_modeswitch &> /dev/null; then
        echo "Installing usb-modeswitch..."
        apt-get update
        apt-get install -y usb-modeswitch usb-modeswitch-data
    fi
    
    # Switch from CD-ROM mode to Ethernet mode
    echo "Switching device from CD-ROM to Ethernet mode..."
    usb_modeswitch -v 0x0bda -p 0x8151 -R
    
    # Wait for kernel to recognize the new mode
    sleep 3
    
    # Reload the ethernet driver
    modprobe -r r8152 2>/dev/null || true
    modprobe r8152
    
    sleep 2
fi

# Wait for eth1 to appear (up to 10 seconds)
echo "Waiting for eth1 interface..."
for i in {1..10}; do
    if ip link show eth1 &>/dev/null; then
        echo "eth1 detected!"
        break
    fi
    echo "Waiting... ($i/10)"
    sleep 1
done

# Verify eth1 exists
if ! ip link show eth1 &>/dev/null; then
    echo "ERROR: eth1 interface not found after mode switch"
    echo "Available interfaces:"
    ip link show
    exit 1
fi

echo "eth1 is ready. Adding to bridge..."

# Ensure bridge exists
if ! ip link show br0 &>/dev/null; then
    echo "Creating bridge br0..."
    brctl addbr br0
    ip addr add 192.168.10.1/24 dev br0
fi

# Remove any IPs from eth0 and eth1
ip addr flush dev eth0 2>/dev/null || true
ip addr flush dev eth1 2>/dev/null || true

# Add interfaces to bridge if not already added
if ! brctl show br0 | grep -q eth0; then
    echo "Adding eth0 to bridge..."
    brctl addif br0 eth0
fi

if ! brctl show br0 | grep -q eth1; then
    echo "Adding eth1 to bridge..."
    brctl addif br0 eth1
fi

# Bring everything up
ip link set dev eth0 up
ip link set dev eth1 up
ip link set dev br0 up

# Enable IP forwarding
sysctl -w net.ipv4.ip_forward=1 >/dev/null

echo ""
echo "Bridge setup complete!"
brctl show
echo ""
echo "Bridge IP:"
ip addr show br0 | grep "inet "
