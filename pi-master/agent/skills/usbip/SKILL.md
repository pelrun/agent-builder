---
name: usbip
description: Attach network-shared USB devices (debug probes, logic analyzers, serial devices) into the container via usbip. Use when the task involves USB hardware, or when a tool reports missing/failed USB device access.
---

# USB devices via usbip

USB devices are **never** mounted from the host. They are attached manually
over the network with usbip: the machine the device is plugged into runs
`usbipd` (exporting it with `usbip bind`), and this container attaches to it.
Devices may be on the host (`host.docker.internal`) or on any other machine
on the network.

## Quick reference

| Command | Purpose |
|---|---|
| `usbip-list` | List devices exported by `$USBIP_HOST` (default `host.docker.internal`) |
| `usbip-list -r <host>` | List devices exported by another machine |
| `usbip-attach -b <busid>` | Attach a device and create its `/dev/bus/usb` node in the container |
| `usbip-detach` | Detach everything and remove the created nodes |
| `usbip-detach -p <port>` | Detach one imported device |

The busid comes from `usbip-list` output (e.g. `1-1.4`).

## Attach procedure

```bash
usbip-list                 # find the busid
usbip-attach -b 1-1.4      # attach; prints the created node path
lsusb                      # device should now be visible to tools
```

`usbip-attach` runs `sudo` internally (the sysfs write needs root). After
attaching, the device is a real USB device on the container's bus: libusb,
pyOCD, OpenOCD, sigrok etc. see it directly. Verify with:

```bash
ls -la /dev/bus/usb/       # node must exist (e.g. /dev/bus/usb/010/003)
python3 -c "open('/dev/bus/usb/010/003','rb')"   # must not raise EPERM
```

Detach when finished — the host regains the device only after detach.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `usbip-attach`: "vhci_hcd is not loaded on the kernel owner (the host)" | client-side kernel module missing | on the **host**: `modprobe vhci_hcd` |
| `usbip: error: could not connect to ...:3240` | `usbipd` not running/reachable on the server machine | on the server: `usbipd -D` (listens on all interfaces; check firewall for port 3240) |
| `usbip: error: import device` | device busy or already attached elsewhere | on the server: `usbip unbind -b <busid>`, re-bind; check `usbip port` for stale imports |
| node exists but open fails with `EPERM` / operation not permitted | container lacks the USB device-cgroup rule | container must be built with the `usbip` feature (usb-cgroup addon); rebuild |
| open fails with `ENXIO` | node points at a device no longer attached | re-attach; `usbip-detach` cleans stale nodes |
| `Read-only file system` on attach | container built without the usb-cgroup addon (sysfs is ro without SYS_ADMIN) | rebuild with the `usbip` feature |

## Host-side management (done manually, not from the container)

```bash
usbip list -l              # local devices with busids
sudo usbip bind -b <busid>     # export a device
sudo usbip unbind -b <busid>   # stop exporting
usbipd -D                  # daemon; listens on all interfaces, port 3240
```

`vhci_hcd` must be loaded on the machine running the *container kernel*
(the host): `modprobe vhci_hcd` (add to `modules-load.d` to persist).
