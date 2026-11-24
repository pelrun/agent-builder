# dcgen — devcontainer generator

`dcgen.py` generates a `.devcontainer/devcontainer.json` by interactively picking
features from a curated catalog. Single file, **Python stdlib only** — no pip
dependencies, runs on any host with Python 3.8+ (the checkbox UI uses `curses`
on POSIX terminals and falls back to numbered prompts everywhere else).

> **See [`CATALOG.md`](CATALOG.md) for the current catalog contents**: feature
> inventory and policies, apt groups, addons (incl. deprecated), presets, the
> collated MCP server inventory, and per-repo migration status.

```
agent-builder/
├── dcgen.py         # the tool (self-contained)
├── catalog.json     # feature catalog + presets (edited, not generated)
├── CATALOG.md       # documentation of the current catalog contents
├── features/        # submodule: source of local features (repo: feature-starter)
├── pi-master/       # master copy of .devcontainer/pi (see "pi config" below)
└── .gitignore       # keeps credential files in pi-master out of git
```

This repo **self-hosts**: its own `.devcontainer/` is generated output
(gitignored) — `python3 dcgen.py --preset agent-builder` reproduces it. The
`.devcontainer/pi/` runtime state bootstraps from `pi-master/` on first
generation and is never touched afterwards.

Local (repo-owned) features are **sourced from the features submodule**
(the feature-starter repo) and copied into the target repo at generation
time. Resolution: `--features-repo` flag or `DCGEN_FEATURES_REPO` env
override, otherwise the catalog candidates (default `features/` next to the
script). If the submodule is missing, run `git submodule update --init`.

## Usage

Run **from the directory you want to generate into** (defaults to cwd):

```bash
python3 dcgen.py                        # interactive wizard
python3 dcgen.py --preset <name>       # reproduce a known config, no prompts
python3 dcgen.py --list                 # dump catalog contents
python3 dcgen.py --preset <name> --dry-run
python3 dcgen.py --preset <name> --verify <repo>/.devcontainer/devcontainer.json
python3 dcgen.py --sync-features        # refresh ./-referenced features from the submodule
python3 dcgen.py --sync-pi              # refresh ./.devcontainer/pi from pi-master
```

| Option | Meaning |
|---|---|
| `target` (positional) | target repo dir, default `.` |
| `--preset NAME` | non-interactive generation from a catalog preset |
| `--name` / `--image` | override project name / base image |
| `--catalog PATH` | alternate catalog (default: `catalog.json` next to the script) |
| `--features-repo PATH` | override features submodule location |
| `--list` | print features, apt groups, addons, presets |
| `--dry-run` | print everything (config + planned copies) without writing |
| `--verify EXISTING` | compare generated result against an existing devcontainer.json; no write; **exit 2** if different |
| `--sync-features` | refresh `./`-referenced local features in target (in place) |
| `--sync-pi` | sync `pi-master/` into `<target>/.devcontainer/pi` (copy-if-older, state-safe) |

Exit codes: `0` ok · `1` usage/catalog error · `2` verify differences.

Interactive input can be interrupted safely: EOF/Ctrl-C at any prompt aborts
without writing.

## What the wizard asks

1. Project name (default: directory name) and base image (default: catalog's).
2. **Language runtimes** — checkbox list. Locked features are *not* shown;
   they are always included.
3. **Tool features** — local features from the features submodule.
4. **apt package groups** — logical groups that merge into one deduplicated
   `apt-packages` entry (locked groups are always on). Afterwards: free-text
   extra packages.
5. **Environment addons** — runArgs / mounts / containerEnv /
   postCreateCommand fragments. Conflicting selections warn (per `conflicts`);
   unselected recommendations (`recommends`) are noted.
6. Option prompts for selected features that define them (locked features are
   never prompted).
7. Review summary → confirm → generate.

## Catalog model

Everything the tool knows lives in `catalog.json`. The catalog is data —
adding a feature, group, addon, or preset needs no code changes. For the
current inventory and per-feature policies, see [`CATALOG.md`](CATALOG.md).

### `features`
| Field | Meaning |
|---|---|
| `kind` | `feature` (published ghcr.io feature, `ref` + `options`) or `local` (lives in the features submodule, referenced as `./features/<id>`) |
| `options` | default feature options; preset/user selections override |
| `prompts` | interactive option questions: `option`, `prompt`, `default`, `proposals` |
| `default` / `locked` | pre-checked in the wizard / always-on, hidden from pickers and prompts |
| `requires` | **feature dependencies** — auto-added with defaults if missing |
| `requires_addons` | **addon dependencies** — auto-selected if missing |
| `requires_packages` | **package dependencies** — merged into the apt-packages entry even if no apt group is selected |

Features are emitted in catalog order, with the merged apt-packages entry
last. Dependency resolution (`requires` / `requires_addons` /
`requires_packages`) is transitive and fails loudly on unknown ids.

### `apt_groups`
Logical package sets merged into **one** `apt-packages:1` entry, deduplicated,
group order preserved. The generated entry carries a provenance comment:

```
// apt packages merged from groups: <groups>; required by features: <pkg> <- <feature, feature>
```

### `addons`
Named JSON fragments merged by kind: `runArgs`, `mounts`, `containerEnv`,
`postCreateCommand`, `remoteUser`/`updateRemoteUserUID`. Extras:
`commented_mounts` / `commented_postcreate` (emitted as `//` lines in presets),
`conflicts`, `recommends`, `requires_path` (warns when a path is missing in
the target), `materializes` (addon ensures a directory is bootstrapped from a
master copy, e.g. pi-config).

### `presets`
Named, non-interactive selections reproducing the existing repo configs:
`name`, `image`, `features` (with options), `apt_groups`, `addons`,
`commented_features` / `commented_mounts` / `commented_postcreate`.

### `features_repo` / `pi_master`
Location candidates for the features submodule (`src/` holds one folder per
feature) and the pi master copy.

## Generation behavior

- Output is JSONC in house style: tab-indented, one `// comment` above each
  feature (from its catalog `comment`) and above the apt entry (provenance).
- Deliberately-disabled entries can be carried in presets and are emitted as
  comments, e.g. `// {"ghcr.io/<org>/<feature>:1": {...}}`.
- Sets (`runArgs`, `mounts`) are deduplicated preserving order; the output is
  re-parsed with the tool's lenient JSONC parser as a self-check.
- Local features are copied from the features submodule into
  `<target>/.devcontainer/features/<id>/` (replacing any existing copy —
  the submodule is the source of truth), and referenced as `"./features/<id>"`.
- Missing target paths referenced by addons produce warnings before writing.

## pi config (`.devcontainer/pi`)

`.devcontainer/pi` is bind-mounted as `~/.pi`, so after first boot it **is**
runtime state. The tool treats it accordingly:

- **Bootstrap only**: generation materializes it from `pi-master/` only when
  the directory is missing or empty. An existing config is never touched by
  regeneration — the tool prints `pi config present ...; untouched`.
- **`--sync-pi` is the explicit updater**: copy-if-older per file (mtime + 1s
  skew tolerance), never deletes target-only files (sessions, caches survive),
  preserves file/dir modes, and mirrors directory modes from master. Because
  `copy2` preserves mtimes, unchanged files stay "kept" on every later sync —
  no churn.
- `pi-master/` holds the shared seed: credentials (gitignored), settings, the
  collated `agent/mcp.json`, model catalogs, skills, tool scripts, and the
  npm extension manifest. Runtime-only artifacts (sessions, missions, caches,
  `*.bak`, `node_modules`) are deliberately absent from master.
- The collated `mcp.json` carries every MCP server used across the managed
  repos; entries not universal to every container ship **disabled** — enable
  per project via a `.pi/mcp.json` override. Flag caveat: pi's key is
  `enabled` (boolean, default true); pi silently ignores unknown keys, so a
  `disabled` key from other clients' conventions does **not** disable
  anything.
- To update repos after changing master config: `python3 dcgen.py --sync-pi
  <repo>`. New repos bootstrap automatically.

## Feature-starter submodule workflow

The features submodule is the source of truth for local features. The
workflow:

1. Author/fix a feature in your feature-starter checkout, bump its
   `devcontainer-feature.json` version, commit **and push**.
2. Bump the pin here: `git submodule update --remote features`, then
   commit the superproject.
3. Propagate: `python3 dcgen.py --sync-features <repo>` refreshes every
   `./`-referenced feature in that repo in place (keeps each repo's existing
   path style), or regenerate the repo with its preset.

## Verifying / migrating existing repos

Presets are parity-checked against the real repos:

```bash
python3 dcgen.py --preset <name> --verify <repo>/.devcontainer/devcontainer.json
```

`--verify` normalizes both sides (apt packages as sets, local feature refs by
basename) and reports only real differences. The lenient parser also accepts
hand-edited files (comments, missing commas, trailing commas). To migrate a
repo, run the same command without `--verify`, review, and commit. See
[`CATALOG.md`](CATALOG.md) for the current expected-diff and migration state.

## Editing the catalog

`catalog.json` is data — no code changes needed to add a group, addon, or
preset. Validate with `python3 dcgen.py --list` and a `--dry-run`. Keep
`locked` entries intact: the tool guarantees them. Update `CATALOG.md`
alongside any catalog change that alters policies or inventories.
