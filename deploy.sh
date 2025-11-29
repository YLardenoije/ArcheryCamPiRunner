#!/bin/bash
# Complete setup script for ArcheryCamPiRunner deployment
# This installs all dependencies, configures the network bridge, and sets up auto-start

set -e

echo "========================================="
echo "ArcheryCamPiRunner Deployment Setup"
echo "========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

INSTALL_DIR="/home/$SUDO_USER/Desktop/ArcheryCamPiRunner"
cd "$INSTALL_DIR" || exit 1

echo "1. Updating system packages..."
echo "-------------------------------"
apt-get update

echo ""
echo "2. Installing system dependencies..."
echo "-------------------------------------"
apt-get install -y python3-pip python3-tk vlc bridge-utils usb-modeswitch usb-modeswitch-data netcat

echo ""
echo "3. Installing Python dependencies..."
echo "-------------------------------------"
pip3 install flask pillow python-vlc --break-system-packages || pip3 install flask pillow python-vlc

echo ""
echo "4. Installing test dependencies (optional)..."
echo "----------------------------------------------"
pip3 install coverage --break-system-packages 2>/dev/null || pip3 install coverage 2>/dev/null || echo "Skipped coverage (optional)"

echo ""
echo "5. Setting up USB Ethernet adapter auto-configuration..."
echo "----------------------------------------------------------"
# Make USB ethernet script executable
chmod +x fix_usb_ethernet.sh

# Install systemd service
cp usb-ethernet-bridge.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable usb-ethernet-bridge.service

echo "USB Ethernet bridge will auto-configure on boot"

echo ""
echo "6. Enabling IP forwarding permanently..."
echo "-----------------------------------------"
if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf; then
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
fi
sysctl -w net.ipv4.ip_forward=1

echo ""
echo "7. Loading r8152 module for USB Ethernet..."
echo "--------------------------------------------"
modprobe r8152 || echo "r8152 module not available (will be loaded by fix script)"
if ! grep -q "r8152" /etc/modules; then
    echo "r8152" >> /etc/modules
fi

echo ""
echo "8. Configuring kiosk application auto-start..."
echo "-----------------------------------------------"

# Create systemd service for kiosk
cat > /etc/systemd/system/kiosk.service << EOF
[Unit]
Description=Archery Kiosk Display
After=network.target usb-ethernet-bridge.service graphical.target
Wants=usb-ethernet-bridge.service

[Service]
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/$SUDO_USER/.Xauthority
Type=simple
User=$SUDO_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/server3.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=graphical.target
EOF

systemctl daemon-reload

# Ask user if they want to enable kiosk auto-start
read -p "Enable kiosk application to start on boot? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    systemctl enable kiosk.service
    echo "Kiosk will start automatically on boot"
else
    echo "Kiosk auto-start disabled (enable later with: sudo systemctl enable kiosk.service)"
fi

echo ""
echo "9. Setting up bridge network now..."
echo "------------------------------------"
./fix_usb_ethernet.sh

echo ""
echo "10. Running network diagnostics..."
echo "-----------------------------------"
chmod +x diagnose_network.sh
./diagnose_network.sh

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Installed components:"
echo "  ✓ Python dependencies (Flask, Pillow, python-vlc)"
echo "  ✓ System packages (VLC, bridge-utils, usb-modeswitch)"
echo "  ✓ Network bridge (192.168.10.1/24)"
echo "  ✓ USB Ethernet adapter auto-configuration"
echo "  ✓ IP forwarding enabled"
echo ""
echo "Services:"
echo "  - usb-ethernet-bridge.service (enabled, runs on boot)"
if systemctl is-enabled kiosk.service &>/dev/null; then
    echo "  - kiosk.service (enabled, runs on boot)"
else
    echo "  - kiosk.service (disabled)"
fi
echo ""
echo "Configuration:"
echo "  - Edit config.py to set RTSP_URL and other settings"
echo "  - Default RTSP: $(grep RTSP_URL config.py | head -1)"
echo "  - Web interface port: $(grep FLASK_PORT config.py | head -1 | grep -o '[0-9]*')"
echo ""
echo "Commands:"
echo "  Start kiosk manually:     python3 server3.py"
echo "  Start kiosk service:      sudo systemctl start kiosk.service"
echo "  Check kiosk status:       sudo systemctl status kiosk.service"
echo "  View kiosk logs:          sudo journalctl -u kiosk.service -f"
echo "  Check bridge status:      brctl show"
echo "  Run diagnostics:          sudo ./diagnose_network.sh"
echo "  Fix bridge manually:      sudo ./fix_usb_ethernet.sh"
echo ""
echo "Next steps:"
echo "  1. Edit config.py with your camera RTSP URL"
echo "  2. Test manually: python3 server3.py"
echo "  3. Access web UI at: http://$(hostname -I | awk '{print $1}'):8080"
echo "  4. Reboot to test auto-start: sudo reboot"
echo ""
