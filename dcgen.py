#!/usr/bin/env python3
"""dcgen - generate a devcontainer.json by interactively picking features from a curated catalog.

Self-contained: Python stdlib only (curses UI on POSIX terminals, plain prompts as fallback).

Layout:
  dcgen.py      - this tool
  catalog.json  - feature/apt-group/addon catalog + presets (next to this file)
  feature-starter (resolved via catalog candidates) - source of local (repo-owned) features.
                  Local features are copied into <target>/.devcontainer/features/<id>/
                  at generation time; the devcontainer.json references them as ./features/<id>.

Usage:
  python3 dcgen.py                        # interactive wizard, generates ./.devcontainer/
  python3 dcgen.py --preset headunit      # reproduce a known config non-interactively
  python3 dcgen.py --list                 # show catalog contents
  python3 dcgen.py --preset blackmagic --verify ../blackmagic/.devcontainer/devcontainer.json
                                          # parity-check a preset against an existing file
  python3 dcgen.py --sync-features        # refresh ./-referenced local features in target

Exit codes: 0 ok, 1 usage/catalog error, 2 verification differences found.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CATALOG = SCRIPT_DIR / "catalog.json"
APT_REF = "ghcr.io/rocker-org/devcontainer-features/apt-packages:1"


class Commented:
    """A JSON value that should be emitted as a //comment instead of real JSON."""
    def __init__(self, payload):
        self.payload = payload


# ---------------------------------------------------------------- lenient JSONC parsing

def strip_jsonc_comments(text: str) -> str:
    """Remove // comments, aware of string literals (URLs stay intact)."""
    out, i, n, in_str, esc = [], 0, len(text), False, False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
        elif c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def parse_jsonc(text: str):
    """Parse a devcontainer.json tolerantly: strips comments, repairs missing commas
    between elements and trailing commas (i.e. survives hand-edited files)."""
    cleaned = strip_jsonc_comments(text)
    repaired = re.sub(r'(["}\]])\s*\n(\s*["{])', r"\1,\n\2", cleaned)
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    return json.loads(repaired)


# ---------------------------------------------------------------- JSONC writing

def _stable_key(x):
    if isinstance(x, Commented):
        x = x.payload
    return json.dumps(x, sort_keys=True, ensure_ascii=False)


def dedupe(seq):
    seen, out = set(), []
    for x in seq:
        k = _stable_key(x)
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def jsonc_dump(obj, key_comments=None):
    """Serialize obj to JSONC text with tabs. key_comments maps tuple paths like
    ('features', 'ghcr.io/...') to a // comment emitted above that key.
    Commented values render as `// <json>` lines."""
    def render(node, path, level):
        pad, pad_in = "\t" * level, "\t" * (level + 1)
        if isinstance(node, dict):
            if not node:
                return ["{}"]
            lines = ["{"]
            items = list(node.items())
            for i, (k, v) in enumerate(items):
                comma = "," if i < len(items) - 1 else ""
                if key_comments and path + (str(k),) in key_comments:
                    lines.append(pad_in + "// " + key_comments[path + (str(k),)])
                if isinstance(v, Commented):
                    commented_entry = {str(k): v.payload}
                    lines.append(pad_in + "// " + json.dumps(commented_entry, ensure_ascii=False))
                else:
                    block = render(v, path + (str(k),), level + 1)
                    if len(block) == 1:
                        lines.append(pad_in + json.dumps(str(k), ensure_ascii=False) + ": " + block[0] + comma)
                    else:
                        lines.append(pad_in + json.dumps(str(k), ensure_ascii=False) + ": " + block[0])
                        block[-1] += comma
                        lines.extend(block[1:])
            lines.append(pad + "}")
            return lines
        if isinstance(node, list):
            if not node:
                return ["[]"]
            lines = ["["]
            for i, v in enumerate(node):
                comma = "," if i < len(node) - 1 else ""
                if isinstance(v, Commented):
                    lines.append(pad_in + "// " + json.dumps(v.payload, ensure_ascii=False))
                else:
                    block = render(v, path + (str(i),), level + 1)
                    if len(block) == 1:
                        lines.append(pad_in + block[0] + comma)
                    else:
                        lines.append(pad_in + block[0])
                        block[-1] += comma
                        lines.extend(block[1:])
            lines.append(pad + "]")
            return lines
        return [json.dumps(node, ensure_ascii=False)]

    return "\n".join(render(obj, (), 0)) + "\n"


# ---------------------------------------------------------------- catalog

def load_catalog(path: Path) -> dict:
    try:
        cat = json.loads(path.read_text())
    except FileNotFoundError:
        sys.exit(f"catalog not found: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"catalog {path} is not valid JSON: {e}")
    for section in ("features", "apt_groups", "addons", "presets"):
        if section not in cat:
            sys.exit(f"catalog missing section: {section}")
    return cat


def resolve_features_repo(catalog: dict, override: str | None):
    candidates = []
    if override:
        candidates.append(Path(override).expanduser())
    env = os.environ.get("DCGEN_FEATURES_REPO")
    if env:
        candidates.append(Path(env).expanduser())
    for cand in catalog.get("features_repo", {}).get("candidates", []):
        p = Path(cand).expanduser()
        if not p.is_absolute():
            p = (SCRIPT_DIR / p).resolve()
        candidates.append(p)
    src_dir = catalog.get("features_repo", {}).get("src_dir", "src")
    for c in candidates:
        if (c / src_dir).is_dir():
            return c / src_dir
    return None


def resolve_pi_master(catalog: dict):
    """Locate the pi-master seed dir (path candidates resolved relative to SCRIPT_DIR)."""
    candidates = []
    env = os.environ.get("DCGEN_PI_MASTER")
    if env:
        candidates.append(Path(env).expanduser())
    for cand in catalog.get("pi_master", {}).get("candidates", []):
        p = Path(cand).expanduser()
        if not p.is_absolute():
            p = (SCRIPT_DIR / p).resolve()
        candidates.append(p)
    for c in candidates:
        if c.is_dir():
            return c
    return None


SYNC_SKEW = 1.0  # seconds of mtime tolerance (clock skew / same-second edits)


def sync_tree(master: Path, dst: Path, dry_run: bool = False):
    """Copy master -> dst, but never overwrite a newer target file and never
    delete target-only files (preserves runtime state). copy2 keeps mtime+mode,
    so an unchanged file compares equal on later syncs. Directory modes are
    mirrored from master (e.g. pi-reach 0700).
    Returns (actions, dst_only_count); actions is a list of (verb, relpath)."""
    actions = []
    master_files = sorted(p for p in master.rglob("*") if p.is_file())
    for src in master_files:
        rel = src.relative_to(master)
        tgt = dst / rel
        if not tgt.exists():
            verb = "created"
        elif src.stat().st_mtime > tgt.stat().st_mtime + SYNC_SKEW:
            verb = "updated"
        else:
            actions.append(("kept", str(rel)))
            continue
        if not dry_run:
            tgt.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, tgt)
        actions.append((verb, str(rel)))
    dst_only = 0
    if dst.is_dir():
        tgt_rels = {str(p.relative_to(dst)) for p in dst.rglob("*") if p.is_file()}
        master_rels = {str(p.relative_to(master)) for p in master_files}
        dst_only = len(tgt_rels - master_rels)
        # mirror directory modes/mtimes from master (files already via copy2)
        if not dry_run:
            for d in [master] + [p for p in master.rglob("*") if p.is_dir()]:
                td = dst / d.relative_to(master)
                if td.is_dir():
                    shutil.copystat(d, td)
    return actions, dst_only


def report_pi_sync(actions, dst_only, target_dir):
    for verb, rel in actions:
        if verb in ("created", "updated"):
            print(f"pi config {verb}: {target_dir}/{rel}")
    kept = sum(1 for a, _ in actions if a == "kept")
    print(f"pi config sync: "
          f"{len([a for a, _ in actions if a == 'created'])} created, "
          f"{len([a for a, _ in actions if a == 'updated'])} updated, "
          f"{kept} kept (target newer/equal), {dst_only} target-only preserved")


def catalog_index(catalog: dict):
    feats = {f["id"]: f for f in catalog["features"]}
    groups = {g["id"]: g for g in catalog["apt_groups"]}
    addons = {a["id"]: a for a in catalog["addons"]}
    return feats, groups, addons


# ---------------------------------------------------------------- config building

def resolve_requires(catalog, spec, warnings):
    """Ensure features' hard requirements are present; add them with default options."""
    known = {f["id"] for f in catalog["features"]}
    selected = set(spec["features"].keys())
    changed = True
    while changed:
        changed = False
        for f in catalog["features"]:
            if f["id"] not in selected:
                continue
            for req in f.get("requires", []):
                if req in selected:
                    continue
                if req not in known:
                    sys.exit(f"feature '{f['id']}' requires unknown feature '{req}' (catalog bug)")
                spec["features"][req] = dict(spec["features"].get(req, {}))
                selected.add(req)
                warnings.append(f"feature '{f['id']}' requires '{req}' - added automatically")
                changed = True


def resolve_addon_requires(catalog, spec, warnings):
    """Ensure features' required addons are present; add them at the end."""
    addons_by_id = {a["id"]: a for a in catalog["addons"]}
    selected = set(spec["addons"])
    changed = True
    while changed:
        changed = False
        for f in catalog["features"]:
            if f["id"] not in spec["features"]:
                continue
            for req in f.get("requires_addons", []):
                if req in selected:
                    continue
                if req not in addons_by_id:
                    sys.exit(f"feature '{f['id']}' requires unknown addon '{req}' (catalog bug)")
                spec["addons"].append(req)
                selected.add(req)
                warnings.append(f"feature '{f['id']}' requires addon '{req}' - added automatically")
                changed = True


def build_config(catalog, spec):
    """spec keys: name, image, features{id:opts}, apt_groups[], extra_packages[],
    addons[], commented_features[], commented_mounts[], commented_postcreate{}, target"""
    feats, groups, addons = catalog_index(catalog)
    key_comments = {}
    warnings = []
    local_ids = []

    resolve_requires(catalog, spec, warnings)
    resolve_addon_requires(catalog, spec, warnings)

    features_obj = {}
    for f in catalog["features"]:
        fid = f["id"]
        commented = fid in spec.get("commented_features", [])
        if fid not in spec["features"] and not commented:
            continue
        opts = dict(f.get("options", {}))
        opts.update(spec["features"].get(fid, {}))
        if f["kind"] == "local":
            ref = f"./features/{fid}"
            local_ids.append(fid)
        else:
            ref = f["ref"]
        features_obj[ref] = Commented(opts) if commented else opts
        if f.get("comment") and not commented:
            key_comments[("features", ref)] = f["comment"]

    pkg_list, group_ids = [], []
    for gid in spec["apt_groups"]:
        if gid not in groups:
            sys.exit(f"unknown apt group: {gid}")
        group_ids.append(gid)
        pkg_list.extend(groups[gid]["packages"])
    pkg_list.extend(spec.get("extra_packages", []))

    # packages hard-required by selected features (e.g. ghidra/jadx -> openjdk-25-jdk)
    required_by = {}
    for f in catalog["features"]:
        if f["id"] in spec["features"]:
            for p in f.get("requires_packages", []):
                required_by.setdefault(p, []).append(f["id"])
    pkg_list.extend(required_by.keys())

    pkg_list = dedupe(pkg_list)
    if pkg_list:
        features_obj[APT_REF] = {"packages": ",".join(pkg_list)}
        if group_ids:
            comment = "apt packages merged from groups: " + " + ".join(group_ids)
        else:
            comment = "apt packages"
        if required_by:
            bits = ", ".join(f"{p} <- {', '.join(ids)}" for p, ids in sorted(required_by.items()))
            comment += "; required by features: " + bits
        if spec.get("extra_packages"):
            comment += f" (+{len(spec['extra_packages'])} extra)"
        key_comments[("features", APT_REF)] = comment

    run_args, mounts = [], []
    container_env, post_create = {}, {}
    for aid in spec["addons"]:
        if aid not in addons:
            sys.exit(f"unknown addon: {aid}")
        a = addons[aid]
        run_args.extend(a.get("runArgs", []))
        mounts.extend(a.get("mounts", []))
        mounts.extend(Commented(m) for m in a.get("commented_mounts", []))
        container_env.update(a.get("containerEnv", {}))
        post_create.update(a.get("postCreateCommand", {}))
        if "remoteUser" in a:
            spec["_remoteUser"] = a["remoteUser"]
            spec["_updateRemoteUserUID"] = True
        rp = a.get("requires_path")
        if rp:
            for req in ([rp] if isinstance(rp, str) else rp):
                if not (Path(spec["target"]) / req).exists():
                    warnings.append(f"addon '{aid}': '{req}' not found in target (mount will dangle)")
        mat = a.get("materializes")
        if mat:
            if resolve_pi_master(catalog) is None:
                warnings.append(f"addon '{aid}': pi-master dir not found; '{mat}' will not be created")
            else:
                spec["_materialize_pi"] = True
    mounts.extend(Commented(m) for m in spec.get("commented_mounts", []))
    for k, v in spec.get("commented_postcreate", {}).items():
        post_create[k] = Commented(v)

    config = {"name": spec["name"], "image": spec["image"]}
    if spec.get("_remoteUser"):
        config["remoteUser"] = spec["_remoteUser"]
        config["updateRemoteUserUID"] = True
    config["features"] = features_obj
    if run_args:
        config["runArgs"] = dedupe(run_args)
    if container_env:
        config["containerEnv"] = container_env
    if post_create:
        config["postCreateCommand"] = post_create
    if mounts:
        config["mounts"] = dedupe(mounts)
    return config, key_comments, local_ids, warnings


# ---------------------------------------------------------------- output

def write_output(target: Path, config, key_comments, local_ids, features_src, dry_run,
                 pi_master=None, materialize_pi=False):
    dc_dir = target / ".devcontainer"
    dc_file = dc_dir / "devcontainer.json"
    text = jsonc_dump(config, key_comments)
    if dry_run:
        print(f"--- would write {dc_file} ---")
        sys.stdout.write(text)
    else:
        dc_dir.mkdir(parents=True, exist_ok=True)
        dc_file.write_text(text)
        print(f"wrote {dc_file}")
    for fid in local_ids:
        src = features_src / fid
        dst = dc_dir / "features" / fid
        if dry_run:
            print(f"--- would copy {src} -> {dst}")
            continue
        if not src.is_dir():
            print(f"WARNING: local feature source missing: {src}", file=sys.stderr)
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"copied feature {fid}: {src} -> {dst}")
    if materialize_pi and pi_master:
        pi_dir = dc_dir / "pi"
        if pi_dir.is_dir() and any(pi_dir.iterdir()):
            print(f"pi config present at {pi_dir}; untouched (use --sync-pi to update from master)")
        else:
            actions, dst_only = sync_tree(pi_master, pi_dir, dry_run)
            if dry_run:
                print(f"--- would bootstrap pi config: {pi_master} -> {pi_dir}")
                for verb, rel in actions:
                    if verb != "kept":
                        print(f"---   pi config {verb}: {pi_dir}/{rel}")
            else:
                report_pi_sync(actions, dst_only, pi_dir)


# ---------------------------------------------------------------- verification

def normalize_feature_opts(opts):
    o = dict(opts)
    if isinstance(o.get("packages"), str):
        o["packages"] = sorted(p for p in o["packages"].split(",") if p)
    return o


def normalize_config(cfg):
    feats = {}
    for ref, opts in cfg.get("features", {}).items():
        if isinstance(opts, Commented):
            continue
        key = Path(ref).name if ref.startswith("./") else ref
        feats[key] = normalize_feature_opts(opts)
    return {
        "name": cfg.get("name"),
        "image": cfg.get("image"),
        "remoteUser": cfg.get("remoteUser"),
        "updateRemoteUserUID": cfg.get("updateRemoteUserUID"),
        "features": feats,
        "runArgs": sorted(str(x) for x in cfg.get("runArgs", [])),
        "containerEnv": cfg.get("containerEnv", {}),
        "postCreateCommand": {k: v for k, v in cfg.get("postCreateCommand", {}).items()
                              if not isinstance(v, Commented)},
        "mounts": sorted(str(x) for x in cfg.get("mounts", []) if not isinstance(x, Commented)),
    }


def verify_configs(gen, existing):
    a, b = normalize_config(gen), normalize_config(existing)
    diffs = []
    for k in ("name", "image", "remoteUser", "updateRemoteUserUID"):
        if a.get(k) != b.get(k):
            diffs.append(f"{k}: generated={a.get(k)!r} existing={b.get(k)!r}")
    for section in ("features", "containerEnv", "postCreateCommand"):
        ga, gb = a[section], b[section]
        for k in sorted(set(ga) | set(gb)):
            if k not in gb:
                diffs.append(f"{section}: only in generated: {k}")
            elif k not in ga:
                diffs.append(f"{section}: only in existing:  {k}")
            elif ga[k] != gb[k]:
                diffs.append(f"{section}[{k}]: generated={ga[k]!r} existing={gb[k]!r}")
    for section in ("runArgs", "mounts"):
        ga, gb = set(a[section]), set(b[section])
        for x in sorted(ga - gb):
            diffs.append(f"{section}: only in generated: {x}")
        for x in sorted(gb - ga):
            diffs.append(f"{section}: only in existing:  {x}")
    return diffs


# ---------------------------------------------------------------- interactive UI

class UI:
    def __init__(self, interactive: bool):
        self.interactive = interactive

    def multi_select(self, title, items, locked=()):
        """items: [{id,label,desc,checked}]. Returns list of selected ids."""
        if not self.interactive:
            return [it["id"] for it in items if it["checked"]]
        state = {it["id"]: bool(it["checked"]) for it in items}
        for lid in locked:
            if lid in state:
                state[lid] = True
        if sys.stdin.isatty() and sys.stdout.isatty():
            try:
                import curses
                return curses.wrapper(self._curses_pick, title, items, state, set(locked))
            except Exception:
                pass  # fall back to plain prompts
        return self._plain_pick(title, items, state, set(locked))

    def _curses_pick(self, stdscr, title, items, state, locked):
        import curses
        curses.curs_set(0)
        cursor = 0
        while True:
            stdscr.erase()
            h, w = stdscr.getmaxyx()
            stdscr.addnstr(0, 0, title, w - 1, curses.A_BOLD)
            stdscr.addnstr(1, 0, "space=toggle  a=all  n=none  arrows=move  enter=confirm", w - 1, curses.A_DIM)
            row = 3
            for i, it in enumerate(items):
                if row >= h - 1:
                    break
                mark = "x" if state[it["id"]] else " "
                lock = " (locked)" if it["id"] in locked else ""
                line = f"[{mark}] {it['label']}{lock}  -  {it.get('desc', '')}"
                stdscr.addnstr(row, 2, line, w - 3, curses.A_REVERSE if i == cursor else 0)
                row += 1
            stdscr.refresh()
            ch = stdscr.getch()
            if ch in (curses.KEY_UP, ord("k")):
                cursor = max(0, cursor - 1)
            elif ch in (curses.KEY_DOWN, ord("j")):
                cursor = min(len(items) - 1, cursor + 1)
            elif ch == ord(" "):
                iid = items[cursor]["id"]
                if iid not in locked:
                    state[iid] = not state[iid]
            elif ch == ord("a"):
                for it in items:
                    state[it["id"]] = True
            elif ch == ord("n"):
                for it in items:
                    if it["id"] not in locked:
                        state[it["id"]] = False
            elif ch in (curses.KEY_ENTER, 10, 13, ord("q")):
                return [it["id"] for it in items if state[it["id"]]]

    def _plain_pick(self, title, items, state, locked):
        while True:
            print(f"\n{title}")
            for i, it in enumerate(items, 1):
                mark = "x" if state[it["id"]] else " "
                lock = " (locked)" if it["id"] in locked else ""
                print(f"  [{mark}] {i:2}) {it['label']}{lock}  -  {it.get('desc', '')}")
            raw = self._input("toggle numbers (e.g. 1 3), a=all, n=none, Enter=done: ").strip().lower()
            if not raw:
                break
            if raw == "a":
                for it in items:
                    state[it["id"]] = True
                continue
            if raw == "n":
                for it in items:
                    if it["id"] not in locked:
                        state[it["id"]] = False
                continue
            for tok in raw.replace(",", " ").split():
                if tok.isdigit() and 1 <= int(tok) <= len(items):
                    iid = items[int(tok) - 1]["id"]
                    if iid not in locked:
                        state[iid] = not state[iid]
        return [it["id"] for it in items if state[it["id"]]]

    def _input(self, prompt):
        try:
            return input(prompt)
        except (EOFError, KeyboardInterrupt):
            print("\naborted")
            sys.exit(0)

    def ask(self, prompt, default):
        if not self.interactive:
            return default
        raw = self._input(f"{prompt} [{default}]: ").strip()
        return raw or default

    def ask_value(self, prompt, default, proposals):
        if not self.interactive:
            return default
        if proposals:
            print(f"\n{prompt}")
            for i, p in enumerate(proposals, 1):
                mark = "*" if p == default else " "
                print(f"  {mark} {i}) {p}")
            raw = self._input(f"choice 1-{len(proposals)} or custom value, Enter={default}: ").strip()
            if not raw:
                return default
            if raw.isdigit() and 1 <= int(raw) <= len(proposals):
                return proposals[int(raw) - 1]
            return raw
        return self.ask(prompt, default)

    def confirm(self, prompt, default=True):
        if not self.interactive:
            return True
        raw = self._input(prompt + (" [Y/n]: " if default else " [y/N]: ")).strip().lower()
        if not raw:
            return default
        return raw in ("y", "yes")


def interactive_spec(catalog, ui, target, feats_src):
    feats, groups, addons = catalog_index(catalog)
    spec = {"target": str(target)}

    spec["name"] = ui.ask("Project name", target.name)
    spec["image"] = ui.ask("Base image", catalog.get("base_image", "mcr.microsoft.com/devcontainers/base:trixie"))

    rt_items = [
        {"id": f["id"], "label": f["id"], "desc": f.get("comment", ""), "checked": f.get("default", False)}
        for f in catalog["features"] if f["kind"] == "feature" and not f.get("locked")
    ]
    selected_rt = ui.multi_select("Language runtimes", rt_items)

    tool_items = [
        {"id": f["id"], "label": f["id"], "desc": f.get("comment", ""), "checked": f.get("default", False)}
        for f in catalog["features"] if f["kind"] == "local" and not f.get("locked")
    ]
    selected_tools = ui.multi_select("Tool features (copied from feature-starter)", tool_items)
    if selected_tools and not feats_src:
        print("WARNING: feature-starter not found; local features cannot be copied.", file=sys.stderr)
    locked_ids = [f["id"] for f in catalog["features"] if f.get("locked")]
    selected = locked_ids + selected_rt + selected_tools

    grp_items = [
        {"id": g["id"], "label": g["id"],
         "desc": ", ".join(g["packages"][:6]) + (" ..." if len(g["packages"]) > 6 else ""),
         "checked": g.get("default", False)}
        for g in catalog["apt_groups"]
    ]
    locked = ["core"] if "core" in groups else []
    selected_groups = ui.multi_select("apt package groups (merged into one apt-packages entry)", grp_items, locked=locked)
    extra_raw = ui.ask("Extra apt packages (comma-separated, blank=none)", "")
    extra = [p.strip() for p in extra_raw.split(",") if p.strip()]

    addon_items = [
        {"id": a["id"], "label": a["id"], "desc": a.get("comment", ""), "checked": a.get("default", False)}
        for a in catalog["addons"]
    ]
    selected_addons = ui.multi_select("Environment addons", addon_items)

    # suggestions from selected tools (addons recommending features and vice versa)
    tools_set = set(selected_tools)
    for a in catalog["addons"]:
        if a["id"] in selected_addons:
            continue
        for rec in a.get("recommends", []):
            if rec in tools_set:
                print(f"note: addon '{a['id']}' is recommended when feature '{rec}' is selected")

    feature_opts = {}
    for fid in selected:
        if feats[fid].get("locked"):
            # locked features: always emitted with catalog default options, no prompts
            feature_opts[fid] = dict(feats[fid].get("options", {}))
            continue
        opts = {}
        for pr in feats[fid].get("prompts", []):
            opts[pr["option"]] = ui.ask_value(pr["prompt"], pr["default"], pr.get("proposals"))
        if opts:
            feature_opts[fid] = opts

    ids = set(selected_addons)
    for aid in selected_addons:
        for c in addons[aid].get("conflicts", []):
            if c in ids:
                print(f"WARNING: conflicting addons selected: {aid} + {c}", file=sys.stderr)

    spec.update({
        "features": feature_opts,
        "apt_groups": selected_groups,
        "extra_packages": extra,
        "addons": selected_addons,
    })
    return spec


# ---------------------------------------------------------------- sync & presets

def sync_features(target: Path, features_src: Path):
    dc_file = target / ".devcontainer" / "devcontainer.json"
    if not dc_file.exists():
        sys.exit(f"no {dc_file}")
    cfg = parse_jsonc(dc_file.read_text())
    refs = [r for r in cfg.get("features", {}) if isinstance(r, str) and r.startswith("./")]
    if not refs:
        print("no local feature references found")
        return
    for ref in refs:
        fid = Path(ref).name
        src = features_src / fid
        dst = dc_file.parent / ref.lstrip("./")
        if not src.is_dir():
            print(f"SKIP {fid}: not in feature-starter ({src})", file=sys.stderr)
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"synced {fid}: {src} -> {dst}")


def preset_spec(catalog, preset_name, target):
    p = catalog["presets"][preset_name]
    return {
        "target": str(target),
        "name": p.get("name", target.name),
        "image": p.get("image", catalog.get("base_image")),
        "features": dict(p.get("features", {})),
        "apt_groups": list(p.get("apt_groups", [])),
        "extra_packages": [],
        "addons": list(p.get("addons", [])),
        "commented_features": list(p.get("commented_features", [])),
        "commented_mounts": list(p.get("commented_mounts", [])),
        "commented_postcreate": dict(p.get("commented_postcreate", {})),
    }


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="devcontainer generator with curated catalog",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("Usage:")[1] if "Usage:" in __doc__ else None)
    ap.add_argument("target", nargs="?", default=".", help="target repo dir (default: cwd)")
    ap.add_argument("--preset", help="use a named preset from the catalog")
    ap.add_argument("--name", help="override project name")
    ap.add_argument("--image", help="override base image")
    ap.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    ap.add_argument("--features-repo", help="path to feature-starter (overrides catalog candidates)")
    ap.add_argument("--list", action="store_true", help="list catalog contents and exit")
    ap.add_argument("--dry-run", action="store_true", help="print instead of writing")
    ap.add_argument("--verify", metavar="EXISTING",
                    help="compare result against an existing devcontainer.json (no write); exit 2 if different")
    ap.add_argument("--sync-features", action="store_true",
                    help="refresh ./-referenced local features in target from feature-starter")
    ap.add_argument("--sync-pi", action="store_true",
                    help="sync pi-master into <target>/.devcontainer/pi (copy-if-older, state-safe)")
    args = ap.parse_args()

    catalog = load_catalog(Path(args.catalog).expanduser().resolve())
    target = Path(args.target).expanduser().resolve()
    feats_src = resolve_features_repo(catalog, args.features_repo)
    pi_master = resolve_pi_master(catalog)
    interactive = sys.stdin.isatty() and sys.stdout.isatty() and not args.preset \
        and not args.verify and not args.sync_features and not args.sync_pi and not args.list
    ui = UI(interactive)

    if args.list:
        for f in catalog["features"]:
            loc = " (local)" if f["kind"] == "local" else ""
            lock = " locked" if f.get("locked") else ""
            req = ""
            if f.get("requires"):
                req += f" [requires: {','.join(f['requires'])}"
                if f.get("requires_addons"):
                    req += f"; addon:{','.join(f['requires_addons'])}"
                if f.get("requires_packages"):
                    req += f"; +{','.join(f['requires_packages'])}"
                req += "]"
            elif f.get("requires_packages"):
                req += f" [needs: {','.join(f['requires_packages'])}]"
            print(f"FEATURE  {f['id']:15} default={'y' if f.get('default') else 'n'}{loc}{lock}{req}  {f.get('comment', '')}")
        for g in catalog["apt_groups"]:
            print(f"APT      {g['id']:15} default={'y' if g.get('default') else 'n'}  {', '.join(g['packages'])}")
        for a in catalog["addons"]:
            print(f"ADDON    {a['id']:18} default={'y' if a.get('default') else 'n'}  {a.get('comment', '')}")
        for name, p in catalog["presets"].items():
            print(f"PRESET   {name:15} features={','.join(p['features'])}  apt={'+'.join(p['apt_groups'])}  addons={','.join(p['addons'])}")
        return 0

    if args.sync_features:
        if not feats_src:
            sys.exit("feature-starter not found (use --features-repo)")
        sync_features(target, feats_src)
        return 0

    if args.sync_pi:
        if not pi_master:
            sys.exit("pi-master dir not found (see catalog 'pi_master')")
        actions, dst_only = sync_tree(pi_master, target / ".devcontainer" / "pi", args.dry_run)
        report_pi_sync(actions, dst_only, target / ".devcontainer" / "pi")
        return 0

    if args.preset:
        if args.preset not in catalog["presets"]:
            sys.exit(f"unknown preset '{args.preset}'. known: {', '.join(catalog['presets'])}")
        spec = preset_spec(catalog, args.preset, target)
    else:
        if not interactive:
            sys.exit("non-interactive without --preset; use --preset or run in a terminal")
        spec = interactive_spec(catalog, ui, target, feats_src)
    if args.name:
        spec["name"] = args.name
    if args.image:
        spec["image"] = args.image
    if not spec.get("image"):
        spec["image"] = catalog.get("base_image")

    config, key_comments, local_ids, warnings = build_config(catalog, spec)
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    if args.verify:
        existing_path = Path(args.verify).expanduser().resolve()
        try:
            existing = parse_jsonc(existing_path.read_text())
        except json.JSONDecodeError as e:
            sys.exit(f"cannot parse {existing_path}: {e}")
        diffs = verify_configs(config, existing)
        if diffs:
            print(f"== {args.preset or spec['name']}: {len(diffs)} difference(s) vs {existing_path}:")
            for d in diffs:
                print("   " + d)
            return 2
        print(f"OK {args.preset or spec['name']}: generated config matches {existing_path}")
        return 0

    if interactive:
        print("\n--- summary ---")
        print(f"name:     {spec['name']}")
        print(f"image:    {spec['image']}")
        print(f"features: {', '.join(spec['features']) or '(none)'}")
        apt_line = " + ".join(spec["apt_groups"]) or "(none)"
        if spec.get("extra_packages"):
            apt_line += f"  + extras: {', '.join(spec['extra_packages'])}"
        print(f"apt:      {apt_line}")
        print(f"addons:   {', '.join(spec['addons']) or '(none)'}")
        if not ui.confirm("Generate devcontainer.json in " + str(target) + "?"):
            print("aborted")
            return 0

    if local_ids and not feats_src:
        sys.exit("local features selected but feature-starter not found (use --features-repo)")
    write_output(target, config, key_comments, local_ids, feats_src, args.dry_run,
                 pi_master=pi_master, materialize_pi=bool(spec.get("_materialize_pi")))
    if not args.dry_run:
        print("\nnext steps:")
        print("  - review .devcontainer/devcontainer.json")
        if local_ids:
            print("  - local features were copied to .devcontainer/features/")
        print("  - optional: npx @devcontainers/cli lock --workspace-folder .")
    return 0


if __name__ == "__main__":
    sys.exit(main())
