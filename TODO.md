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
