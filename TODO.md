# TODO

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

## Generalize the pi seed machinery (de-couple dcgen from pi)

dcgen is agent-agnostic everywhere except the config-seed machinery, which is
single-instance and pi-branded. Not needed while the fleet is pi-standardized,
but keep in mind for changes that touch generation, addons, or sync.

- **Current coupling** (audited 2026-11-26): `resolve_pi_master()` reads the
  `pi_master` catalog key + `DCGEN_PI_MASTER` env; `write_output()` hardcodes
  the materialization destination `.devcontainer/pi`; the addon `materializes`
  value is only a trigger, never the destination; `--sync-pi` syncs the same
  hardcoded dir; the `_materialize_pi` spec flag allows exactly one
  materializable dir.
- **Already catalog-swappable**: the agent itself is plain data — the `pi`
  feature (locked, `requires: node`) with its identity in
  `features/pi/install.sh`, the `pi-config` addon (mount + env), and preset
  references. A custom catalog can already replace pi as the installed agent;
  docker auto-creates missing bind sources, so an unseeded config dir works
  but boots empty (no credential seeding).
- **Design direction when needed**: honor each addon's `materializes` value as
  the destination; resolve a master dir per addon (per-addon key like
  `materializes_from`, or a top-level `seed_dirs` map); rename `--sync-pi` →
  generic `--sync-seed` (keep `--sync-pi` as alias during migration).
  `sync_tree()` semantics (bootstrap-only, copy-if-older, never delete
  target-only files) are already generic — reuse as-is.
- **Constraint while making other changes**: don't deepen the coupling — no
  new code paths that assume the seed dir is pi's, no second use of
  `_materialize_pi`, keep addon seed semantics data-driven.
- **Trigger**: implement when a second agent needs a seeded config dir
  (the point of the machinery is seeding gitignored credentials, not the
  mount itself).
- Effort: small — ~30-line refactor plus catalog schema docs; migration is
  free (`.devcontainer/` is regenerated output).

## Seed feature-scoped agent notes as pi skills

Agent-generated tooling notes (first instance: `GHIDRA_MCP_NOTES.md`, operator
procedures for ghidrassist headless driving) should ship into containers that
select the owning feature, formatted as pi skills so agents discover them
automatically.

- **Format: skills, not bare docs.** These notes are task-triggered
  instructions — exactly the skill shape. Progressive disclosure: pi puts only
  name + description in the system prompt and loads the body on match;
  `/skill:name` forces loading. Bare files have no discovery story — the
  agent must be told they exist. Description quality decides routing (state
  what it does AND when it applies; malformed SKILL.md / missing description
  = silently not loaded).
- **Carriage: the feature dir.** `features/<id>/skills/<name>/SKILL.md`
  (+ bundled `references/`); installed by `install.sh` to
  `/usr/local/share/agent-notes/skills/<name>/` (build time, root-owned,
  survives the container image). Appears exactly when the feature is
  selected; versioned and propagated with the feature via `--sync-features`.
- **Discovery: the pi `skills` setting.** pi-master `settings.json` gains
  `"skills": ["/usr/local/share/agent-notes/skills"]` — one universal line
  (the setting is universal; the content stays feature-scoped, respecting
  the pi-master policy). Project-level settings in a repo's `.devcontainer/pi`
  could override/extend.
- **Trap**: features must NOT write into `~/.pi` at build time — `pi-config`
  bind-mounts `.devcontainer/pi` over it after boot, masking image content.
  Hence the `/usr/local/share` hop.
- **Conditional install**: option-aware where it matters — e.g. ghidra
  feature installs the ghidrassist notes only when `MCPSERVER=ghidrassist`
  (the doc is stack-specific; ghidramcp would contradict it).
- **Rejected alternatives**: runtime bind-mount of the feature's docs dir
  (needs a hidden addon per feature + `requires_addons`, against the
  addons-only-on-commonality policy; no-rebuild updates are its one upside);
  pi-master skills (universal scope for feature-specific content); bare
  `/usr/local/share` docs without skill format (no routing).
- **Doc churn** requires a container rebuild to land (same as any
  build-time-baked content); regeneration alone is not enough.
- **Trigger**: implement when the first note is ready to ship (move
  `GHIDRA_MCP_NOTES.md` into `features/ghidra/skills/`, add frontmatter,
  conditional copy, bump feature version, add the settings line, propagate).
- Effort: small — an install.sh copy block + one settings line per fleet;
  frontmatter authoring is the real work.
