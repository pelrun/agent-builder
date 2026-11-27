# Changelog

Historical record of notable changes. The primary docs (README.md,
CATALOG.md, AGENTS.md) describe current state only.

## 2026-11-26

- Onboarded `cisco-camera-control` as a catalog preset: common base + ghidra
  (default `ghidrassist` MCP) and the new `host-network` addon
  (`--network=host`, for LAN-local camera access). Regenerating the repo
  adds the fleet-wide `TZ` containerEnv and `git-credential-libsecret`
  (fleet default, absent from its hand-maintained config); `--verify`
  passes.
- Presets can now carry `extra_packages` (merged into the apt entry after
  addon packages; round-tripped by `--show`/save-preset, shown by `--list`,
  and pre-seeded by `--modify` — previously the wizard silently dropped a
  base spec's extras). The "cannot be captured" save-preset warning is gone.
  Policy: per-agent packages/mounts go straight into the preset; promote to
  an apt group or addon only when multiple presets share the need.
- Folded agent drift back in: `polywork-mounts` gains the
  cisco-camera-control repo mount; the cisco preset carries its
  firmware-inspection extras (cpio, mtools, qemu-user-static,
  squashfs-tools, u-boot-tools). Both repos regenerate to `--verify` OK.
- Extra-mount inputs now rewrite home shorthands to `${localEnv:HOME}`
  (leading `~`, `$HOME`, `${HOME}` in the source; applied in the wizard and
  again at generation time for stored presets). Bare home roots (`~`,
  `$HOME`) and sources that keep a shell shorthand (`~user/...`) warn —
  docker cannot resolve shell expansion in bind sources; only
  `${localEnv:...}`/`${localWorkspaceFolder}` survive verbatim.

## 2026-11-25

- usbip investigation resolved: device attachment is managed on the host
  (devices are not permanently connected), so no container-side usbip
  component is needed — usbip-attached (vhci) devices land on the host bus
  like physical ones and surface through `usb-hotplug`'s existing
  /dev/bus/usb mount + cgroup rule. Verified empirically: the container
  shares the host kernel's sysfs (host USB devices visible) but not its
  devtmpfs, so device nodes never propagate into a container's private
  /dev without the bind-mount.

- Catalog cleanup: removed the deprecated ghidra addons (`ghidra-mount`,
  `ghidra-home-env`, `ghidra-mcp-bridge`) and `pi-env` (its env vars moved
  into `pi-config`). Presets migrated to the ghidra feature (blepoolsensor
  selects `MCPSERVER=ghidramcp`; headunit drops the mount; nas-cleanup
  intentionally drops Ghidra entirely).
- Documentation restructure: agent-facing fine print split into AGENTS.md;
  docs now carry current state only, history lives here.
- `--show`: print any selection (`--preset` / `--refresh` / wizard) as a
  paste-ready catalog.json preset entry; interactive generation ends with
  an offer to save the configuration as a preset (id prompt, overwrite
  confirmation; extras and custom images are warned as not capturable).
- `--verify` reports apt package differences as set differences (only the
  packages unique to each side) instead of dumping both package lists.
- `--modify [PRESET]`: re-run the wizard pre-seeded from a specified or
  detected preset — all-defaults modify regenerates a byte-identical config.
  Also fixes a wizard bug where prompt-less selected features (usbip) were
  dropped, and prompt answers equal to the shown default are no longer
  stored as redundant overrides.
- Wizard: `hidden` property for addons — never shown in the pickers, for
  addons that exist only to be auto-selected (`usb-cgroup`).
- Extra workspace mounts: presets gain an optional `extra_mounts` list
  (merged after addon mounts) and the wizard asks for them — a bare host
  path is shorthand for `source=<path>,target=/workspaces/<basename>,type=bind`.
  `--list` marks presets carrying them.
- Catalog-wide `containerEnv` support; sets `TZ: Australia/Melbourne` in
  every generated container (the container clock was previously UTC, so
  commits recorded UTC dates after local midnight).
- `usbip` feature + `usb-cgroup` addon: network-shared USB devices attach
  manually from the container (host or remote machines) with zero
  /dev/bus mounts — the helper mknods the node locally and the addon's
  device-cgroup rule allows opening it. Host side: usbipd + modprobe
  vhci_hcd.
- USB addons replaced: `usb-hotplug` / `usb-basic` (host /dev/bus mounts)
  removed from the catalog; blepoolsensor and cpc-workspace presets migrated
  to the `usbip` feature + `usb-cgroup` addon. The addon bind-mounts the
  host's vhci sysfs dir onto its canonical path (rw bind — the container's
  own sysfs is read-only, and vhci attach is a sysfs write; no SYS_ADMIN)
  and carries the USB device-cgroup rule. `vhci_hcd` must be loaded on the
  host before container creation. `usbip` skill added to pi-master.

## 2026-11-24

- `git-credential-libsecret` addon: host libsecret credential helper over
  D-Bus (helper built post-create from git's contrib, `credential.useHttpPath`
  for per-repo credential scoping); added to the agent-builder preset.
- Wizard: catalog `comment` split into a short one-liner plus optional
  `help`, shown on `h`; apt entry comment now lists only groups + addons.
- `--verify` works standalone: the wizard (or preset re-apply prompt) can
  supply the configuration to compare.
- `--refresh` re-applies the preset matching an existing devcontainer, with
  detection precedence: `// generated by dcgen from preset:` marker, then
  config `name`, then directory name.
- Features flattened: the feature-starter submodule is gone; local features
  live in `features/` (one dir per feature) in this repo.

## Migration history (from the original repo configs, now complete)

Expected-diff notes from `--verify` against the managed repos, resolved as
the presets were adopted:

- **All presets**: pi migration — `./features/pi` feature added, the old
  pi-agent post-create removed.
- **blackmagic**: devcontainer name fixed (`car-headunit` → `blackmagic`);
  arm-embedded group corrected (`binutils-arm-none-eabi`,
  `gdb-multiarch` added).
- **headunit**: apt dedupe (`dexdump`, `vim`, `xxd` were listed twice).
- **blepoolsensor**: invalid package `arm-none-eabi-gcc` (a binary name, not
  a Debian package) replaced by `gcc-arm-none-eabi` + `python3-pyocd`.
- Data quirk absorbed by the lenient parser: nas-cleanup's original
  devcontainer.json had a missing comma.
