# TODO

## usbip feature (network-attached USB devices)

Investigation done (2026-11-26); awaiting decision on host-side prerequisites.
Key finding: usbip complements rather than replaces the usb addons — vhci
devices surface through the same /dev/bus/usb usbfs mechanics, so the
bind-mount + cgroup rule (usb-hotplug) is still what makes the container see
them. Design:

- **`usbip` feature** (local, `features/usbip`): installs the `usbip` package
  (already in trixie; client + server in one pkg), ships PATH helpers
  `usbip-list` / `usbip-attach <busid>` / `usbip-detach` defaulting to
  `USBIP_HOST` or `host.docker.internal`; attach helper pre-checks vhci_hcd
  (clear error pointing at host `modprobe vhci_hcd`), cleans stale ports,
  runs the sysfs write via sudo (common-utils provides it).
- Feature declares `requires_addons: [usb-hotplug]` so visibility is
  auto-selected. `usb-basic` can be retired later (hotplug is a superset).
- **Host prerequisites**: `usbipd` listening on the docker bridge
  (currently connection-refused on 172.17.0.1:3240 — firewall allowance for
  172.17.0.0/16 :3240) and `modprobe vhci_hcd` once (host modules-load.d;
  container has no /lib/modules). Host kernel is Arch; usbip's kernel
  interface is stable across distro versions (userspace 2.0 is fine).
- Caveats: TCP-tunneled USB — fine for serial/JTAG/debug/logic-analyzer,
  poor for isochronous devices; vhci SuperSpeed support is kernel-dependent;
  attaching on the host instead needs zero container changes (usb-hotplug
  already suffices).

## Split apt into per-group/per-addon features for layer caching

Replace the single merged `apt-packages:1` entry with generated local
features, one per apt group / addon `apt_packages` set / extras, so a package
edit only rebuilds its own Docker layer instead of the whole apt set.

- **Mechanism**: `features` object keys are unique — the rocker
  `apt-packages:1` ref cannot repeat. dcgen instead generates
  `.devcontainer/features/apt-<group>/` (and `apt-<addon>`, `apt-extra`)
  two-file features (`devcontainer-feature.json` + `install.sh`), referenced
  as `./features/apt-<id>`; each gets its own layer.
- **Packages stay catalog-sourced**: `catalog.json` remains the single source
  of truth; generated install.sh files bake the list in (`apt-get update &&
  apt-get install -y --no-install-recommends <pkgs>`).
- `apt-get update` in every layer (no cross-layer index coupling); clean
  `/var/lib/apt/lists` only in the final apt layer.
- Generated dirs must be **excluded from `--sync-features`** (dcgen output,
  not submodule content) — match on a `apt-` prefix or a marker file.
- `--verify` keeps working via existing basename normalization; migration is
  free (`.devcontainer/` is gitignored output, re-run dcgen per repo).
- Expected gain: modest — the current single entry is emitted last, so its
  invalidation already stops at one layer. Split narrows "re-run all apt
  installs" (~30-60s) to "re-run the touched group" (~5-15s); bigger win if
  features ever get ordered after apt, or for volatile `extras`.
- Effort: moderate — template + copy path in `write_output`, sync exclusion,
  verify dry-run.
