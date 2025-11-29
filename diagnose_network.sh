#!/bin/bash
# Network and camera connectivity diagnostics

echo "========================================="
echo "Network Bridge Diagnostics"
echo "========================================="
echo ""

echo "1. Bridge Status:"
echo "-----------------"
brctl show
echo ""

echo "2. IP Addresses on all interfaces:"
echo "-----------------------------------"
ip addr show br0 2>/dev/null || echo "br0: NOT FOUND"
echo ""
ip addr show eth0 | grep -E "inet |flags"
echo ""
ip addr show eth1 | grep -E "inet |flags"
echo ""

echo "3. Routing Table:"
echo "-----------------"
ip route
echo ""

echo "4. ARP Cache (devices seen on network):"
echo "----------------------------------------"
arp -n
echo ""

echo "5. IP Forwarding Status:"
echo "------------------------"
sysctl net.ipv4.ip_forward
echo ""

echo "6. Auto-discovering cameras on 192.168.10.0/24 network:"
echo "--------------------------------------------------------"
echo "Scanning for active hosts (this may take 10-15 seconds)..."

# First, do a quick ping sweep to populate ARP cache
for i in {2..254}; do
    # Skip .1 (gateway) and do background pings
    if [ $i -ne 1 ]; then
        ping -c 1 -W 1 192.168.10.$i >/dev/null 2>&1 &
    fi
done
wait

# Extract cameras from ARP cache (exclude gateway and incomplete entries)
CAMERAS=($(arp -n | grep "192.168.10\." | grep -v "192.168.10.1" | grep -v "incomplete" | awk '{print $1}' | sort -u))

echo "Found ${#CAMERAS[@]} device(s) on 192.168.10.x network (excluding gateway):"
if [ ${#CAMERAS[@]} -eq 0 ]; then
    echo "  No devices found. Cameras may not be responding to ping."
    echo "  You can manually specify IPs: $0 <camera1_ip> <camera2_ip>"
else
    for cam in "${CAMERAS[@]}"; do
        MAC=$(arp -n | grep "^$cam " | awk '{print $3}')
        echo "  - $cam (MAC: $MAC)"
    done
fi
echo ""

# Get camera IPs from discovered list or user arguments
if [ ${#CAMERAS[@]} -ge 1 ]; then
    CAMERA1="${1:-${CAMERAS[0]}}"
else
    CAMERA1="${1:-192.168.10.31}"
fi

if [ ${#CAMERAS[@]} -ge 2 ]; then
    CAMERA2="${2:-${CAMERAS[1]}}"
else
    CAMERA2="${2:-192.168.10.33}"
fi

echo "7. Testing Cameras:"
echo "-------------------"
echo "Camera 1: $CAMERA1"
ping -c 3 -W 2 $CAMERA1 2>&1 | tail -4
echo ""

echo "Camera 2: $CAMERA2"
ping -c 3 -W 2 $CAMERA2 2>&1 | tail -4
echo ""

echo "8. Camera Port Scan (RTSP typically on 554):"
echo "---------------------------------------------"
if command -v nc &> /dev/null; then
    echo "Checking $CAMERA1:554 (RTSP)..."
    timeout 3 nc -zv $CAMERA1 554 2>&1
    echo ""
    echo "Checking $CAMERA2:554 (RTSP)..."
    timeout 3 nc -zv $CAMERA2 554 2>&1
    echo ""
    echo "Checking $CAMERA1:80 (HTTP)..."
    timeout 3 nc -zv $CAMERA1 80 2>&1
    echo ""
    echo "Checking $CAMERA2:80 (HTTP)..."
    timeout 3 nc -zv $CAMERA2 80 2>&1
else
    echo "nc (netcat) not installed. Install with: sudo apt-get install netcat"
fi
echo ""

echo "9. Determining which physical port each camera is connected to:"
echo "-----------------------------------------------------------------"
for cam in "${CAMERAS[@]}"; do
    echo "Checking $cam..."
    
    # Send ping to populate ARP cache
    ping -c 1 -W 1 $cam >/dev/null 2>&1
    
    # Listen on each interface for traffic from this camera
    ETH0_TRAFFIC=$(timeout 2 tcpdump -i eth0 -c 1 host $cam 2>/dev/null | wc -l)
    ETH1_TRAFFIC=$(timeout 2 tcpdump -i eth1 -c 1 host $cam 2>/dev/null | wc -l)
    
    if [ "$ETH0_TRAFFIC" -gt 0 ]; then
        echo "  ✓ $cam is connected to eth0 (built-in Ethernet)"
    elif [ "$ETH1_TRAFFIC" -gt 0 ]; then
        echo "  ✓ $cam is connected to eth1 (USB-to-LAN adapter)"
    else
        echo "  ✗ $cam - No traffic detected on either interface (camera may be offline)"
    fi
done
echo ""

echo "10. Listening on eth0 for ARP requests (5 seconds):"
echo "---------------------------------------------------"
echo "This will show if cameras are trying to find the gateway..."
timeout 5 tcpdump -i eth0 -n arp 2>/dev/null | grep "who-has" || echo "No ARP traffic detected"
echo ""

echo "11. Listening on eth1 for ARP requests (5 seconds):"
echo "---------------------------------------------------"
timeout 5 tcpdump -i eth1 -n arp 2>/dev/null | grep "who-has" || echo "No ARP traffic detected"
echo ""

echo "12. Bridge Interface Packet Counters:"
echo "--------------------------------------"
echo "Check RX/TX on each interface to see which is receiving traffic:"
cat /sys/class/net/br0/statistics/rx_packets 2>/dev/null && echo "br0 RX packets: $(cat /sys/class/net/br0/statistics/rx_packets)"
cat /sys/class/net/eth0/statistics/rx_packets 2>/dev/null && echo "eth0 RX packets: $(cat /sys/class/net/eth0/statistics/rx_packets)"
cat /sys/class/net/eth1/statistics/rx_packets 2>/dev/null && echo "eth1 RX packets: $(cat /sys/class/net/eth1/statistics/rx_packets)"
echo ""

echo "========================================="
echo "Diagnostics Complete"
echo "========================================="
echo ""
echo "Usage: $0 [camera1_ip] [camera2_ip]"
echo "Example: $0 192.168.10.31 192.168.10.32"
echo ""
echo "Common Issues:"
echo "- If eth0/eth1 have IP addresses: They shouldn't! Only br0 should have an IP"
echo "- If ping works but RTSP doesn't: Check camera credentials and RTSP URL"
echo "- If ARP requests seen but no response: Bridge may not be forwarding properly"
echo "- If one camera works but not the other: Check which interface each is connected to"
