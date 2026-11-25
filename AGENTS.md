# AGENTS.md — machine-facing rules and invariants

The fine print for coding agents working in this repo. Human-facing docs:
[`README.md`](README.md) (usage) and [`CATALOG.md`](CATALOG.md) (current
catalog inventory). Deferred design work lives in [`TODO.md`](TODO.md);
historical record lives in [`CHANGELOG.md`](CHANGELOG.md).

## What this repo is

`dcgen.py` (Python stdlib only) generates devcontainer configs for a set of
managed repos from `catalog.json`. This repo **self-hosts**: its own
`.devcontainer/` is generated output (gitignored) — never hand-edit it.
Change the catalog/presets, then `python3 dcgen.py --refresh .`.

## Editing the catalog

`catalog.json` is data — adding or changing features, apt groups, addons, or
presets needs no code changes. Rules:

- Validate every change: `python3 dcgen.py --list` (parses the catalog and
  dumps the inventory), plus `--preset <name> --dry-run` for each affected
  preset, and `--refresh --verify` this repo's config when touching the
  `agent-builder` preset.
- `locked` entries are guarantees, not defaults: always installed, hidden
  from pickers and prompts. Do not remove or weaken them.
- `comment` is the one-line wizard description (keep it to one line);
  put detail into the optional `help` string (shown on `h` in the pickers).
  The `//` comments in generated configs use `comment` only.
- Update `CATALOG.md` alongside any change that alters inventories or
  policies; record deferred design work in `TODO.md` rather than code
  comments, and notable change history in `CHANGELOG.md`. The primary docs
  (README/CATALOG/AGENTS) describe current state only — no historical
  narrative, migration stories, or "was X, now Y" notes.
- New presets can be authored without hand-editing: an interactive wizard
  run offers to save the configuration as a preset, and
  `python3 dcgen.py --preset <name> --show` prints any selection as a
  paste-ready catalog.json preset entry. Always validate a new preset with
  `--preset <id> --dry-run` (and `--verify` against the source container
  if there is one).

## Catalog schema

Top-level `containerEnv` is merged into every generated config's
`containerEnv` (catalog first, addons after and may override) — e.g. the
universal `TZ: Australia/Melbourne`.

### `features`
| Field | Meaning |
|---|---|
| `kind` | `feature` (published ghcr.io feature, `ref` + `options`) or `local` (lives in `features/`, referenced as `./features/<id>`) |
| `options` | default feature options; preset/user selections override |
| `prompts` | interactive option questions: `option`, `prompt`, `default`, `proposals` |
| `default` / `locked` | pre-checked in the wizard / always-on (see above) |
| `comment` / `help` | wizard line / `h` help; `comment` doubles as the generated `//` comment |
| `requires` | feature dependencies — auto-added with defaults if missing |
| `requires_addons` | addon dependencies — auto-selected if missing |
| `requires_packages` | package dependencies — merged into the apt entry even if no apt group is selected |

Features are emitted in catalog order (also the build order), with the
merged apt-packages entry last. Dependency resolution
(`requires` / `requires_addons` / `requires_packages`) is transitive and
fails loudly on unknown ids.

### `apt_groups`
Logical package sets merged into **one** `apt-packages:1` entry:
selected groups first (catalog order), then feature `requires_packages`,
then addon `apt_packages`, then extras — deduplicated preserving
first-seen order. The entry carries a provenance comment listing only
sources:

```
// apt packages merged from groups: <groups>; addons: <addons> (+N extra)
```

Per-package provenance lives in the feature/addon definitions (comment /
help), never in generated files.

### `addons`
Named JSON fragments merged by kind: `runArgs`, `mounts`, `containerEnv`,
`postCreateCommand` (merged into one object, keyed by the fragment names the
addons declare), `remoteUser`/`updateRemoteUserUID`. Extras:
`apt_packages` (addon-level package dependencies), `commented_mounts` /
`commented_postcreate` (emitted as `//` lines), `conflicts` (selection
warns), `recommends` (unselected-but-relevant notes),
`requires_path` (warns when a path is missing in the target),
`materializes` (bootstraps a directory from a master copy, e.g. pi-config),
`hidden` (never shown in the wizard pickers — for addons that exist only to
be auto-selected via `requires_addons`; presets may still list them
explicitly, and `--list` shows them with a `hidden` marker).
Addons carry `comment` / `help` like features.

### `presets`
Named, non-interactive selections reproducing existing repo configs:
`name`, `image`, `features` (with options), `apt_groups`, `addons`,
`extra_mounts` (workspace mounts merged after addon mounts; the wizard
prompts for them, accepting bare host paths as shorthand for
`source=<path>,target=/workspaces/<basename>,type=bind`),
`commented_features` / `commented_mounts` / `commented_postcreate`
(deliberately-disabled entries emitted as `// {...}` lines so they survive
regeneration as documentation).

### `features_repo` / `pi_master`
Location candidates for the features dir (one folder per feature; the
repo's `features/` is the default candidate, joined with `src_dir`) and the
pi master copy. Resolution order: `--features-repo` flag >
`DCGEN_FEATURES_REPO` env > catalog candidates; `DCGEN_PI_MASTER` env >
`pi_master` candidates.

## Generation semantics

`--modify [PRESET]` re-runs the wizard pre-seeded from a preset: every
picker starts with the preset's selections checked, option prompts default
to the preset's option values, and existing extra mounts are kept. Selected
features are always emitted, storing only prompt answers that differ from
the shown default (this also keeps prompt-less features like `usbip`, which
were previously dropped by the wizard).

- Output house style: tab-indented JSONC, one `// comment` above each
  feature (from its catalog `comment`) and above the apt entry (provenance).
- `runArgs` and `mounts` are deduplicated preserving order; the finished
  text is re-parsed with the tool's lenient JSONC parser as a self-check
  before writing.
- Local features are copied from the features dir into
  `<target>/.devcontainer/features/<id>/`, **replacing any existing copy**
  (the features dir is the source of truth), and referenced as
  `"./features/<id>"`.
- Missing target paths referenced by addons produce warnings before writing.
- Preset detection (`--refresh` / interactive re-apply offer), most
  authoritative first: the `// generated by dcgen from preset: <id>` marker
  (only if that preset still exists — survives project/directory renames),
  then the config `name` field, then the directory name.

## Local features (`features/`)

- One dir per feature; this repo is the source of truth.
- Bump the feature's `devcontainer-feature.json` version when behavior
  changes.
- Propagate edits: `python3 dcgen.py --sync-features <repo>` refreshes every
  `./`-referenced feature in that repo in place (keeps each repo's existing
  path style), or regenerate the repo with its preset.

## pi config state (`.devcontainer/pi`)

`.devcontainer/pi` is bind-mounted as `~/.pi`, so after first boot it **is**
runtime state:

- **Bootstrap only**: generation materializes it from `pi-master/` only when
  the directory is missing or empty. An existing config is never touched by
  regeneration.
- **`--sync-pi` is the explicit updater**: copy-if-older per file (mtime +
  1s skew tolerance), never deletes target-only files (sessions, caches
  survive), preserves file/dir modes, mirrors directory modes from master.
  `copy2` preserves mtimes, so unchanged files stay "kept" on later syncs —
  no churn.
- `pi-master/` holds the shared seed: settings, the collated
  `agent/mcp.json`, model catalogs, skills, tool scripts, the npm extension
  manifest, and gitignored credentials (`auth.json`, `models-store.json`,
  `pi-reach/`). Runtime-only artifacts (sessions, missions, caches,
  `*.bak`, `node_modules`) must never be added to master.
- `agent/mcp.json` collates every MCP server used across the managed repos;
  entries not universal to every container ship **disabled** and are enabled
  per project via a `.pi/mcp.json` override. New servers go into master
  **disabled** with provenance in the description. pi's flag is `enabled`
  (boolean, default true) — pi silently ignores unknown keys, so a
  `disabled` key from other clients' conventions does **not** disable
  anything.

## Verify

- `--preset <name> --verify <repo>/.devcontainer/devcontainer.json`
  compares without writing; **exit 2** on differences.
- Normalization before compare: apt `packages` compared as sets, local
  feature refs keyed by basename, commented entries ignored, `runArgs`/
  `mounts` as sorted sets — cosmetic edits don't false-positive.
- The lenient parser accepts comments and missing/trailing commas.
