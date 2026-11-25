#!/usr/bin/env bash

set -e

USBIP_HOST=${HOST:-"host.docker.internal"}

export DEBIAN_FRONTEND=noninteractive

echo "Installing usbip client..."
apt-get update
apt-get install -y --no-install-recommends usbip

echo "Installing helpers..."
install -m 0755 "$(dirname "$0")/bin/usbip-attach" /usr/local/bin/usbip-attach
install -m 0755 "$(dirname "$0")/bin/usbip-detach" /usr/local/bin/usbip-detach
install -m 0755 "$(dirname "$0")/bin/usbip-list" /usr/local/bin/usbip-list

# runtime default for the helpers (feature options are not visible post-build)
mkdir -p /etc/profile.d
cat > /etc/profile.d/usbip.sh <<EOF
export USBIP_HOST=${USBIP_HOST}
EOF

echo "usbip client installed."
echo "Note: attaching requires vhci_hcd on the kernel owner (the host):"
echo "  modprobe vhci_hcd   # and usbipd listening on the network"
