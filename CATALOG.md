# Catalog contents & state

Companion to [`README.md`](README.md): documents the *current* content of
`catalog.json`, the pi-master seed, and the migration status of the managed
repos. Update this file alongside any catalog change that alters policies,
inventories, or migration state.

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

Policies:

- **`java` feature deliberately absent.** The ghcr.io java feature is far
  slower to build than installing `openjdk-25-jdk` as a package — use the
  `jdk` apt group (or `android-re`, which includes it).
- **`pi` is locked** (always installed, hidden from pickers and prompts,
  version `latest`) with node as a hard feature dependency.
- **`ghidra`** installs Ghidra to `/opt/ghidra` (download URL resolved via the
  GitHub releases API — release filenames embed a build date, so the URL is
  not derivable from the version) plus an MCP server selected by the
  `mcpServer` option (feature env `MCPSERVER`, default **`ghidrassist`**):

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

Selected groups merge into one deduplicated `apt-packages` entry (core first,
order preserved, provenance comment emitted).

## Addons

Active: `host-gateway`, `usb-hotplug` / `usb-basic` (mutually exclusive),
`host-ipc`, `gui-bridge` (X11/Wayland), `pi-env`, `pi-config` (bootstraps +
mounts `.devcontainer/pi`), `ghidra-mount`, `ghidra-home-env`, `ssh-mount`,
`uv`, `ghidra-mcp-bridge`, `remote-user`, `polywork-mounts` (machine-specific
cross-repo mounts used by agent-builder), and `git-credential-libsecret` —
host libsecret credential helper via D-Bus Secret Service: installs
`libsecret-1-0` (+ `libsecret-1-dev` / `libglib2.0-dev` build deps as
`apt_packages`), mounts the host session bus
(`$XDG_RUNTIME_DIR/bus` → `/tmp/host-dbus/bus`) with
`DBUS_SESSION_BUS_ADDRESS` set, and builds `git-credential-libsecret`
post-create from git's `contrib/credential/libsecret` (Debian does not ship
the binary) into `~/.local/bin`, registering it as a global credential
helper. Pairs with the host `.gitconfig` that devcontainers copy in.

Deprecated — pending migration of the repos that still use them; do not
select for new containers:

| Addon | Superseded by |
|---|---|
| `ghidra-mount` | ghidra feature (installs to `/opt/ghidra`) |
| `ghidra-home-env` | ghidra feature (sets `GHIDRA_INSTALL_DIR` itself); never combine with the feature — it would override `/opt/ghidra` |
| `ghidra-mcp-bridge` | bundled in the ghidra feature |

## Presets

| Preset | Adds beyond the common base* |
|---|---|
| `agent-builder` | `polywork-mounts` (cross-repo mounts, machine-specific) |
| `blackmagic` | arm-embedded packages |
| `blepoolsensor` | renode 1.17.0, jdk/arm-embedded/logic-analyzer groups, remote-user, usb-hotplug, host-ipc, gui-bridge, ghidra-mount + ghidra-home-env, ssh-mount, uv, ghidra-mcp-bridge |
| `cpc-workspace` | cpc-build packages, usb-basic (commented-out cpctelera post-create preserved) |
| `headunit` | ghidra + jadx 1.5.6, arm-embedded/arm-cross-binutils/android-re groups, ghidra-mount |
| `nas-cleanup` | usb-basic, ghidra-mount + ghidra-home-env, ssh-mount |

\* common base in every preset: `base:trixie`, common-utils, node 26, python
os-provided, **pi feature**, core apt group, host-gateway, pi-config. The
`pi-env` addon is present in all presets except blepoolsensor and nas-cleanup
(their original configs never set those variables).

## pi-master MCP inventory (`agent/mcp.json`)

Every MCP server used across the managed repos is collated here; only the
universally-used ones are enabled.

| Server | Source repos | State |
|---|---|---|
| `zai-search`, `zai-reader`, `zai-zread`, `zai-vision` | all | **enabled** |
| `docling` (PDF→markdown, uvx) | agent-builder, blackmagic, headunit | disabled |
| `ghidra` (bethington bridge, :8089, `MCPSERVER=ghidramcp`) | blepoolsensor | disabled |
| `ghidrassist` (native, :8080/mcp, `MCPSERVER=ghidrassist`) | — (new default) | disabled |
| `gdb` (gdb-mcp v0.4.0) | blepoolsensor | disabled |
| `logic-analyzer` (project-bound cwd → blepoolsensor) | blepoolsensor | disabled |

Enable per project without touching master via a `.pi/mcp.json` override,
e.g. `{"mcpServers": {"docling": {"enabled": true}}}`. New servers must be
added to master **disabled**, with provenance in the description. pi's key is
`enabled` — a `disabled` key is silently ignored and the server still
connects.

## Migration & parity status

`--verify` against the existing repos currently shows only intentional diffs:

- **All presets**: pi migration (`+ ./features/pi`, `− pi-agent postCreate`).
- **blackmagic**: name fix (`car-headunit` → `blackmagic`) + two added arm
  packages (`binutils-arm-none-eabi`, `gdb-multiarch` — the latter is a
  dependency of `gcc-arm-none-eabi` anyway).
- **headunit**: apt dedupe (`dexdump`, `vim`, `xxd` were listed twice).
- **blepoolsensor**: invalid package `arm-none-eabi-gcc` (a binary name, not
  a Debian package) replaced by `gcc-arm-none-eabi` + `python3-pyocd`.

Pending migrations (presets deliberately keep the deprecated addons until
done): blepoolsensor, nas-cleanup, headunit → switch ghidra-mount/env/bridge
addons to the ghidra feature, then remove the deprecated addon entries from
the catalog.

Known data issues in the originals, preserved as-is until migrated:
nas-cleanup's original file had a missing comma (invalid JSON — the lenient
parser repairs it); blepoolsensor's mcp.json/auth/models-store diverge from
master (see the pi-master MCP note above).
