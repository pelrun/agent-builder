# Catalog contents & state

Companion to [`README.md`](README.md): documents the *current* content of
`catalog.json`, and the pi-master seed. Editing rules and invariants live in [`AGENTS.md`](AGENTS.md).

## Features

Emitted in catalog order (this is also the build order, with the merged
apt-packages entry last):

| Feature | Kind | Notes |
|---|---|---|
| `common-utils` | ghcr.io | locked on — non-root user + sudo + CLI utils |
| `node` | ghcr.io | v26 default, no pnpm; global npm installs work without sudo |
| `python` | ghcr.io | `os-provided` (matches apt python3), no tooling |
| `pi` | local, **locked** | pi coding agent, npm global (`--ignore-scripts`); hard `requires: node` |
| `renode` | local | portable simulator; version option |
| `jadx` | local | dex decompiler; `requires_packages: openjdk-25-jdk` |
| `ghidra` | local | see below |
| `usbip` | local | usbip client + `usbip-list`/`usbip-attach`/`usbip-detach` helpers; manually attach devices shared by the host or any remote machine; creates the node in-container via mknod (no /dev/bus mount); `requires_addons: usb-cgroup` |

Policies:

- **`java` feature deliberately absent.** The ghcr.io java feature is far
  slower to build than installing `openjdk-25-jdk` as a package — use the
  `jdk` apt group instead.
- **`pi` is locked** (always installed, hidden from pickers and prompts,
  version `latest`) with node as a hard feature dependency.
- **`ghidra`** installs Ghidra plus an MCP server selected by the
  `mcpServer` option:

  | Option | Stack | Transport | Notes |
  |---|---|---|---|
  | `ghidrassist` (default) | symgraph/GhidrAssistMCP — native MCP server extension, no bridge | HTTP :8080 (`/mcp` streamable + `/sse`) | release assets are built **per Ghidra minor version**; the installer picks the matching one (exact API-version match) |
  | `ghidramcp` | bethington fork — extension + python bridge (installed via `uv tool` → `/usr/local/bin/bridge-mcp-ghidra`; uv self-provisioned at build time) | HTTP API :8089 behind the stdio bridge | pinned release v7.0.0, built against Ghidra **12.1.4** (bump when a release targets the newer Ghidra) |

  Both paths: extension unpacked into `Ghidra/Extensions/` (headless
  auto-enables), one-time PyGhidra enrollment for the target user, and a few
  unauthenticated GitHub API calls per build. GhidrAssistMCP headless: start
  via the `GAMCPStartServerScript.java` pre-script (`analyzeHeadless ...
  -preScript GAMCPStartServerScript.java "host=127.0.0.1" "port=8080"`).

## apt groups

| Group | Packages | Notes |
|---|---|---|
| `core` (locked) | build-essential, binutils, file, kitty-terminfo, xxd, vim, ripgrep, jq, curl, unzip, less | common toolset in every container |
| `arm-embedded` | gcc-arm-none-eabi, binutils-arm-none-eabi, gdb-multiarch, python3-pyocd | Cortex-M toolchain + debug |
| `arm-cross-binutils` | binutils-aarch64-linux-gnu, binutils-arm-linux-gnueabihf | cross-object inspection only |
| `android-re` | aapt, apktool, dexdump, libsmali-java, zstd, ltrace, adb, e2fsprogs, openjdk-25-jdk, python3-capstone, libcapstone-dev | Android RE; includes the JDK |
| `logic-analyzer` | sigrok-cli, sigrok-firmware-fx2lafw | sigrok CLI |
| `cpc-build` | bison, flex, clang, libboost-dev, zlib1g-dev, libfreeimage-dev | SDCC/CPCtelera build deps |
| `jdk` | openjdk-25-jdk | standalone JDK |

Selected groups currently merge into one deduplicated `apt-packages` entry.

## Addons

Default ✓ = pre-checked in the wizard.

| Addon | Default | Notes |
|---|---|---|
| `host-gateway` | ✓ | `host.docker.internal` resolves to the host |
| `usb-hotplug` | | USB passthrough, incl. devices plugged in later or attached via usbip on the host (conflicts with `usb-basic`) |
| `usb-basic` | | USB passthrough, devices present at start only (conflicts with `usb-hotplug`) |
| `usb-cgroup` | | device-cgroup rule for dynamically created USB nodes (major 189) — no mounts; required by the `usbip` feature |
| `host-ipc` | | share the host IPC namespace |
| `gui-bridge` | | X11/Wayland GUI apps from the host display |
| `pi-config` | ✓ | bind-mount the repo's `.devcontainer/pi` as `~/.pi` (materialized from `pi-master`) |
| `ssh-mount` | | bind-mount host `~/.ssh` — for HTTPS git auth prefer `git-credential-libsecret` |
| `uv` | | install `uv` (post-create) |
| `remote-user` | | run as `vscode` user, match host UID |
| `polywork-mounts` | | machine-specific: mount the other repos into `/workspaces` (host layout `~/github/*`, `~/Projects/*`) |
| `git-credential-libsecret` | ✓ | host libsecret credential helper over D-Bus: mounts the host session bus, builds the helper post-create from git's `contrib` (Debian does not ship the binary), registers it globally with `credential.useHttpPath` (per-repo credential scoping); pairs with the host `.gitconfig` that devcontainers copy in |

## Presets

| Preset | Adds beyond the common base* |
|---|---|
| `agent-builder` | `polywork-mounts` (cross-repo mounts, machine-specific) |
| `blackmagic` | arm-embedded group |
| `blepoolsensor` | renode 1.17.0, ghidra feature (`MCPSERVER=ghidramcp`), jdk/arm-embedded/logic-analyzer groups, usb-hotplug, host-ipc, gui-bridge, ssh-mount, uv |
| `cpc-workspace` | cpc-build group, usb-basic |
| `headunit` | ghidra + jadx 1.5.6, arm-embedded/arm-cross-binutils/android-re groups |
| `nas-cleanup` | ssh-mount |

\* common base in every preset: `base:trixie`, common-utils, node 26, python os-provided,
**pi feature**, core apt group, host-gateway, pi-config, git-credential-libsecret.

## pi-master MCP inventory (`agent/mcp.json`)

Every MCP server used across the managed repos is collated here; only the
universally-used ones are enabled.

| Server | Source repos | State |
|---|---|---|
| `zai-search`, `zai-reader`, `zai-zread`, `zai-vision` | all | **enabled** |
| `docling` (PDF→markdown, uvx) | agent-builder, blackmagic, headunit | disabled |
| `ghidra` (bethington bridge, :8089, `MCPSERVER=ghidramcp`) | blepoolsensor | disabled |
| `ghidrassist` (native, :8080/mcp, `MCPSERVER=ghidrassist`) | — (default) | disabled |
| `gdb` (gdb-mcp v0.4.0) | blepoolsensor | disabled |
| `logic-analyzer` (project-bound cwd → blepoolsensor) | blepoolsensor | disabled |

Enable per project without touching master via a `.pi/mcp.json` override,
e.g. `{"mcpServers": {"docling": {"enabled": true}}}`.
