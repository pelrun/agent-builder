# dcgen — devcontainer generator

`dcgen.py` generates a `.devcontainer/devcontainer.json` by interactively picking
features from a curated catalog. Single file, **Python stdlib only** — no pip
dependencies, runs on any host with Python 3.8+ (the checkbox UI uses `curses`
on POSIX terminals and falls back to numbered prompts everywhere else).

```
agent-builder/
├── dcgen.py         # the tool (self-contained)
├── catalog.json     # feature catalog + presets (edited, not generated)
├── pi-master/       # master copy of .devcontainer/pi (see "pi config" below)
└── .gitignore       # keeps credential files in pi-master out of git
```

This repo **self-hosts**: its own `.devcontainer/` is generated output
(gitignored) — `python3 dcgen.py --preset agent-builder` reproduces it,
including the pi feature and the cross-repo `polywork-mounts` addon. The
`.devcontainer/pi/` runtime state bootstraps from `pi-master/` on first
generation and is never touched afterwards.

Local (repo-owned) features are **sourced from feature-starter** — the canonical
feature repo — and copied into the target repo at generation time. The catalog
finds feature-starter by trying candidates in order (paths with `~` are host
home, bare paths are relative to this file's directory):

1. `--features-repo` CLI flag / `DCGEN_FEATURES_REPO` env var
2. `../feature-starter` (sibling layout: works in devcontainers and `~/github/*`)
3. `~/github/feature-starter`, `~/Projects/feature-starter`

## Usage

Run **from the directory you want to generate into** (defaults to cwd):

```bash
python3 dcgen.py                        # interactive wizard
python3 dcgen.py --preset headunit      # reproduce a known config, no prompts
python3 dcgen.py --list                 # dump catalog contents
python3 dcgen.py --preset blackmagic --dry-run
python3 dcgen.py --preset blackmagic --verify ../blackmagic/.devcontainer/devcontainer.json
python3 dcgen.py --sync-features        # refresh ./-referenced features from feature-starter
python3 dcgen.py --sync-pi              # refresh ./.devcontainer/pi from pi-master
```

| Option | Meaning |
|---|---|
| `target` (positional) | target repo dir, default `.` |
| `--preset NAME` | non-interactive generation from a catalog preset |
| `--name` / `--image` | override project name / base image |
| `--catalog PATH` | alternate catalog (default: `catalog.json` next to the script) |
| `--features-repo PATH` | override feature-starter location |
| `--list` | print features, apt groups, addons, presets |
| `--dry-run` | print everything (config + planned copies) without writing |
| `--verify EXISTING` | compare generated result against an existing devcontainer.json; no write; **exit 2** if different |
| `--sync-features` | refresh `./`-referenced local features in target from feature-starter (in place) |
| `--sync-pi` | sync `pi-master/` into `<target>/.devcontainer/pi` (copy-if-older, state-safe) |

Exit codes: `0` ok · `1` usage/catalog error · `2` verify differences.

Interactive input can be interrupted safely: EOF/Ctrl-C at any prompt aborts
without writing.

## What the wizard asks

1. Project name (default: directory name) and base image (default: catalog's).
2. **Language runtimes** — checkbox list. Locked features (`common-utils`, `pi`)
   are *not* shown; they are always included.
3. **Tool features** — local features from feature-starter (renode, jadx, ghidra).
4. **apt package groups** — logical groups that merge into one deduplicated
   `apt-packages` entry (`core` is locked on). Afterwards: free-text extra packages.
5. **Environment addons** — runArgs / mounts / containerEnv /
   postCreateCommand fragments. Conflicting selections (e.g. both USB flavors)
   warn; missing recommendations (e.g. ghidra selected without `ghidra-mount`)
   are noted.
6. Version prompts for selected features that define them (locked features are
   never prompted).
7. Review summary → confirm → generate.

## Catalog model

Everything the tool knows lives in `catalog.json`:

### `features`
| Field | Meaning |
|---|---|
| `kind` | `feature` (published ghcr.io feature, `ref` + `options`) or `local` (lives in feature-starter, referenced as `./features/<id>`) |
| `options` | default feature options; preset/user selections override |
| `prompts` | interactive version questions: `option`, `prompt`, `default`, `proposals` |
| `default` / `locked` | pre-checked in the wizard / always-on, hidden from pickers and prompts |
| `requires` | **feature dependencies** — auto-added with defaults if missing (e.g. `pi` requires `node`) |
| `requires_packages` | **package dependencies** — merged into the apt-packages entry even if no apt group is selected (e.g. `ghidra`/`jadx` require `openjdk-25-jdk`) |

Emitted in catalog order: `common-utils → node → python → pi → renode → jadx →
ghidra`, with apt-packages last. Note: the `java` *feature* is intentionally
absent — installing `openjdk-25-jdk` as a package (see `jdk` group) is far
faster to build than the ghcr.io java feature.

### `apt_groups`
Logical package sets merged into **one** `apt-packages:1` entry, deduplicated,
group order preserved. `core` is the common toolset (locked on). The generated
entry carries a provenance comment:

```
// apt packages merged from groups: core + arm-embedded + android-re; required by features: openjdk-25-jdk <- jadx, ghidra
```

### `addons`
Named JSON fragments merged by kind: `runArgs`, `mounts`, `containerEnv`,
`postCreateCommand`, `remoteUser`/`updateRemoteUserUID`. Extras:
`commented_mounts` (emitted as `// "..."` lines, like the esphome mount in
agent-builder), `conflicts`, `recommends`, `requires_path` (warns when a path is
missing in the target), `materializes` (pi-config bootstraps `.devcontainer/pi`).

### `presets`
Named, non-interactive selections reproducing the existing repo configs:
`name`, `image`, `features` (with options), `apt_groups`, `addons`,
`commented_features` / `commented_mounts` / `commented_postcreate`.

| Preset | Adds beyond the common base* |
|---|---|
| `agent-builder` | `polywork-mounts` (cross-repo mounts, machine-specific) |
| `blackmagic` | arm-embedded packages |
| `blepoolsensor` | renode 1.17.0, jdk/arm-embedded/logic-analyzer, remote-user, usb-hotplug, host-ipc, gui-bridge, ghidra-mount + env, ssh, uv, ghidra-mcp-bridge |
| `cpc-workspace` | cpc-build packages, usb-basic (commented-out cpctelera post-create preserved) |
| `headunit` | ghidra + jadx 1.5.6, android-re/arm packages, ghidra-mount |
| `nas-cleanup` | usb-basic, ghidra-mount + home-env, ssh mount |

\* common base in every preset: `base:trixie`, common-utils, node 26, python
os-provided, **pi feature**, core apt group, host-gateway, pi-config. The
`pi-env` addon is present in all presets except blepoolsensor and nas-cleanup
(their original configs never set those variables).

### `features_repo` / `pi_master`
Location candidates for feature-starter (`src/` subdir holds one folder per
feature) and the pi master copy.

## Generation behavior

- Output is JSONC in house style: tab-indented, one `// comment` above each
  feature (from its catalog `comment`) and above the apt entry (provenance).
- Deliberately-disabled entries can be carried in presets and are emitted as
  comments, e.g. `// {"ghcr.io/devcontainers/features/java:1": {...}}`.
- Sets (`runArgs`, `mounts`) are deduplicated preserving order; the output is
  re-parsed with the tool's lenient JSONC parser as a self-check.
- Local features are copied from feature-starter into
  `<target>/.devcontainer/features/<id>/` (replacing any existing copy —
  feature-starter is the source of truth), and referenced as `"./features/<id>"`.
- Missing target paths referenced by addons produce warnings before writing.

## pi config (`.devcontainer/pi`)

`.devcontainer/pi` is bind-mounted as `~/.pi`, so after first boot it **is**
runtime state. The tool treats it accordingly:

- **Bootstrap only**: generation materializes it from `pi-master/` only when
  the directory is missing or empty. An existing config is never touched by
  regeneration — the tool prints `pi config present ...; untouched`.
- **`--sync-pi` is the explicit updater**: copy-if-older per file (mtime + 1s
  skew tolerance), never deletes target-only files (sessions, caches survive),
  preserves file/dir modes (`auth.json` 0600, `pi-reach/` 0700), and mirrors
  directory modes from master. Because `copy2` preserves mtimes, unchanged
  files stay "kept" on every later sync — no churn.
- `pi-master/` contains the shared credential set (`auth.json`,
  `models-store.json` — both providers, `pi-reach/identity.json`) plus config
  (settings, mcp.json, models.json, skills, bin, npm manifest). The
  credential files are listed in this repo's `.gitignore` — if you ever turn
  agent-builder into a git repo, they stay untracked.
- **MCP servers are collated in master** (`agent/mcp.json`): every server used
  by any repo is present, but only the `zai-*` tools are enabled — everything
  else (`docling`, `ghidra`, `gdb`, `logic-analyzer`) carries
  `"enabled": false` with provenance in its `description`. Enable a server
  where needed without touching master: add a project-level override in the
  repo's `.pi/mcp.json` (e.g. `{"mcpServers": {"docling": {"enabled": true}}}`),
  which pi layers over the user-level entry. New servers must be added to
  master disabled. Flag caveat: pi's key is `enabled` (boolean, default true).
  Other MCP clients use a `disabled` key — pi ignores unknown keys silently,
  so `"disabled": true` does NOT disable anything; the server still connects.
- Runtime-only artifacts (sessions, missions, mcp caches, crashes, `*.bak`,
  `npm/node_modules`) are deliberately absent from master.

To update repos after changing master config: `python3 dcgen.py --sync-pi <repo>`
(or add the flag to a regeneration run). New repos bootstrap automatically.

## Feature-starter relationship

feature-starter is the source of truth for local features (`pi`, `renode`,
`jadx`, `ghidra`). The workflow:

1. Edit/fix a feature in `feature-starter/src/<id>/`, bump its
   `devcontainer-feature.json` version, commit.
2. Propagate: `python3 dcgen.py --sync-features <repo>` refreshes every
   `./`-referenced feature in that repo in place (keeps each repo's existing
   path style), or regenerate the repo with its preset.
3. The ghidra feature installs Ghidra **plus the GhidraMCP stack**: the
   GhidraMCP extension (unpacked into `Ghidra/Extensions/`, auto-enabled
   headless), the MCP bridge (pinned fork release, installed system-wide via
   `uv tool` → `/usr/local/bin/bridge-mcp-ghidra`; uv is self-provisioned at
   build time since features run before post-create, and declared in the
   catalog as `requires_addons: ["uv"]` so the uv addon is auto-selected), and
   one-time PyGhidra enrollment for the target user (piped y/y answers to
   ghidra's own launcher). The bridge is therefore bundled — the separate
   `ghidra-mcp-bridge` addon is deprecated (kept only in the blepoolsensor
   preset until that repo migrates), and the master mcp.json ghidra entry
   points at `/usr/local/bin/bridge-mcp-ghidra`. Expect a few unauthenticated
   GitHub API calls per build (ghidra release + ghidra-mcp release assets).

## Verifying / migrating existing repos

Presets are parity-checked against the real repos:

```bash
python3 dcgen.py --preset headunit --verify ../headunit/.devcontainer/devcontainer.json
```

`--verify` normalizes both sides (apt packages as sets, local feature refs by
basename) and reports only real differences. Currently the expected,
intentional diffs for every preset are the pi migration (`+ ./features/pi`,
`− pi-agent postCreate`); plus: blackmagic name fix + two added arm packages,
headunit apt dedupe, blepoolsensor replacing the invalid `arm-none-eabi-gcc`
package with `gcc-arm-none-eabi` + `python3-pyocd`. To migrate a repo, run the
same command without `--verify`, review, and commit.

The lenient parser also accepts hand-edited files (comments, missing commas,
trailing commas) — the nas-cleanup original had an invalid missing comma and
still verified.

The `ghidra-mount` and `ghidra-home-env` addons are **deprecated** — the
ghidra feature (installs to `/opt/ghidra`, sets `GHIDRA_INSTALL_DIR` itself)
supersedes them. They remain in the blepoolsensor/nas-cleanup/headunit presets
until those repos are migrated; don't select them for new containers, and
never combine `ghidra-home-env` with the ghidra feature (the addon would
override the feature's `/opt/ghidra`).

## Editing the catalog

`catalog.json` is data — no code changes needed to add a group, addon, or
preset. Validate with `python3 dcgen.py --list` and a `--dry-run`. Keep locked
entries (`common-utils`, `pi`, `core`) intact: the tool guarantees them, and
dependency resolution (`requires` / `requires_packages`) is transitive and
fails loudly on unknown ids.
