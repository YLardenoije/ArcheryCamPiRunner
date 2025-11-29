#!/bin/bash
# Setup persistent bridge configuration for eth0 and eth1 using netplan/interfaces
# This makes the bridge configuration survive reboots

set -e

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

echo "Setting up persistent bridge configuration..."

# Install bridge-utils
if ! command -v brctl &> /dev/null; then
    echo "Installing bridge-utils..."
    apt-get update
    apt-get install -y bridge-utils
fi

# Check if using netplan or interfaces
if [ -d "/etc/netplan" ] && [ "$(ls -A /etc/netplan/*.yaml 2>/dev/null)" ]; then
    echo "Detected netplan configuration..."
    
    # Backup existing netplan config
    mkdir -p /etc/netplan/backup
    cp /etc/netplan/*.yaml /etc/netplan/backup/ 2>/dev/null || true
    
    # Create netplan bridge config
    cat > /etc/netplan/01-bridge.yaml << 'EOF'
network:
  version: 2
  renderer: networkd
  
  ethernets:
    eth0:
      dhcp4: false
      dhcp6: false
    eth1:
      dhcp4: false
      dhcp6: false
  
  bridges:
    br0:
      interfaces: [eth0, eth1]
      addresses:
        - 192.168.10.1/24
      parameters:
        stp: false
        forward-delay: 0
EOF
    
    echo "Created /etc/netplan/01-bridge.yaml"
    echo "Applying netplan configuration..."
    netplan apply
    
else
    echo "Using /etc/network/interfaces configuration..."
    
    # Backup existing interfaces file
    cp /etc/network/interfaces /etc/network/interfaces.backup.$(date +%Y%m%d_%H%M%S)
    
    # Check if bridge config already exists
    if grep -q "br0" /etc/network/interfaces; then
        echo "Bridge configuration already exists in /etc/network/interfaces"
        echo "Skipping modification (backup created)"
    else
        # Append bridge configuration
        cat >> /etc/network/interfaces << 'EOF'

# Bridge configuration for eth0 and eth1
auto eth0
iface eth0 inet manual

auto eth1
iface eth1 inet manual

auto br0
iface br0 inet static
    address 192.168.10.1
    netmask 255.255.255.0
    bridge_ports eth0 eth1
    bridge_stp off
    bridge_fd 0
    bridge_maxwait 0
EOF
        
        echo "Added bridge configuration to /etc/network/interfaces"
        echo "Restarting networking service..."
        systemctl restart networking
    fi
fi

# Enable IP forwarding permanently
if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf; then
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
    sysctl -p
    echo "IP forwarding enabled permanently"
fi

echo ""
echo "Persistent bridge setup complete!"
echo ""
echo "Bridge status:"
brctl show
echo ""
echo "IP addresses:"
ip -4 addr show br0
echo ""
echo "The bridge will persist after reboot."
echo "To verify after reboot, run: brctl show"
