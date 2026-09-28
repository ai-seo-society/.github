"""uv run python -m profilegen <command>

  update    refresh + build + check: the one to run after anything changed in the org
  sync      clone missing org repos into the workspace (../), fast-forward clean ones
  refresh   read the org from GitHub into data/org.json
  build     render profile/README.md and profile/assets/ from catalog + data
  check     every gate; --live also compares data/org.json with GitHub
  preview   write .preview/profile.html: the page as GitHub renders it, light and dark

--ci      output for a public log (the autopilot): never names a repo the catalog lacks

Exit codes
  0  the page is current and complete
  1  a gate failed: do not publish
  2  gh, git or config trouble
  4  the page is current, but a repo members can see has no catalog entry yet
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import art, build, live, preview, privacy
from .catalog import CatalogError, load_catalog, load_snapshot, unshown
from .readme import TemplateError

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT.parent
NEEDS_WORDS = 4
PREVIEW = ROOT / ".preview" / "profile.html"


def _catalog():
    return load_catalog(ROOT / build.CATALOG, set(art.MOTIFS))


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def cmd_sync(dry_run: bool) -> int:
    report = live.sync(_catalog().org, WORKSPACE, dry_run)
    print("\n".join(report) or "nothing to do")
    print(f"\nworkspace: {WORKSPACE}{'  (dry run: nothing changed)' if dry_run else ''}")
    return 1 if any(line.startswith("FAILED") for line in report) else 0


def _describe_change(old: dict | None, new: dict) -> list[str]:
    if old is None:
        return [f"first snapshot: {len(new['repos'])} repositories"]
    before = {r["name"]: r for r in old["repos"]}
    after = {r["name"]: r for r in new["repos"]}
    lines = [f"now on the page: {n}" for n in sorted(set(after) - set(before))]
    lines += [f"off the page: {n}" for n in sorted(set(before) - set(after))]
    for n in sorted(set(before) & set(after)):
        a, b = before[n], after[n]
        if a["tier"] != b["tier"]:
            lines.append(f"{n}: tier {a['tier']} -> {b['tier']}")
        if a["empty"] and not b["empty"]:
            lines.append(f"{n}: first commit landed, leaves 'On the way'")
        old_tags = {x["tag"] for x in a["releases"]}
        lines += [f"{n}: released {x['tag']}" for x in b["releases"] if x["tag"] not in old_tags]
    return lines or ["data/org.json: no change"]


def _say_pending(pending: list[str], ci: bool) -> None:
    if not pending:
        return
    if ci:
        print(f"WAITING  {len(pending)} repositor{'y' if len(pending) == 1 else 'ies'} members can see "
              "have no catalog entry yet. Run the org-profile skill.")
    else:
        for name in pending:
            print(f"WAITING  {name}: members can see it, but catalog.yaml has no entry. "
                  f"Write one from ../{name}/README.md, then run `update`.")


def cmd_refresh(dry_run: bool, ci: bool) -> list[str]:
    catalog = _catalog()
    snap, pending, notes = live.fetch_snapshot(catalog.org, set(catalog.entries), redact=ci)
    path = ROOT / build.SNAPSHOT
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    for line in _describe_change(old, snap):
        print(line)
    for note in notes:
        print(f"note     {note}")
    _say_pending(pending, ci)
    if not dry_run:
        _write(path, json.dumps(snap, indent=2, ensure_ascii=False) + "\n")
    return pending


def cmd_build() -> int:
    rendered = build.render_all(ROOT)
    changed = build.drift(ROOT, rendered)
    for rel in changed:
        _write(ROOT / rel, rendered[rel])
    stale = build.stale_files(ROOT, rendered)
    for rel in stale:
        (ROOT / rel).unlink()
    print("\n".join([f"wrote    {r}" for r in changed] + [f"removed  {r}" for r in stale]) or "already current")
    return 0


def cmd_check(compare_live: bool, ci: bool = False, just_refreshed: bool = False) -> int:
    fails, notes, passed = [], [], []
    try:
        rendered = build.render_all(ROOT)
        catalog = _catalog()
        passed.append("catalog and data/org.json agree")
    except (CatalogError, TemplateError) as e:
        print(f"FAIL  catalog / template\n      {str(e).replace(chr(10), chr(10) + '      ')}")
        return 1
    for name in unshown(catalog, load_snapshot(ROOT / build.SNAPSHOT)):
        notes.append(f"not shown: {name} (members cannot see it now: renamed, deleted, or not released yet)")

    drifted = build.drift(ROOT, rendered) + build.stale_files(ROOT, rendered)
    if drifted:
        fails.append("out of date, run `build`: " + ", ".join(drifted))
    else:
        passed.append(f"README and {len(rendered) - 1} images equal a fresh build")

    files = {**live.committable_files(ROOT), **{k: v.encode("utf-8") for k, v in rendered.items()}}
    deny_text = live.denylist_text()
    rules = privacy.deny_rules(deny_text) if deny_text is not None else []
    findings = privacy.scan(files, rules)
    if findings:
        fails.append("privacy: " + "; ".join(map(str, findings)))
    elif deny_text is None:
        notes.append(f"privacy: no deny-list on this machine, so only the secret rules ran over {len(files)} files")
    else:
        passed.append(f"privacy: deny-list ({len(rules)} rules) and secret rules clean over {len(files)} files")

    pending: list[str] = []
    if compare_live:
        fresh, pending, _ = live.fetch_snapshot(catalog.org, set(catalog.entries), redact=ci)
        current = json.loads((ROOT / build.SNAPSHOT).read_text(encoding="utf-8"))
        if fresh != current:
            fails.append("data/org.json is behind GitHub: " + "; ".join(_describe_change(current, fresh)))
        else:
            passed.append("data/org.json equals what GitHub says now")
    elif just_refreshed:
        passed.append("data/org.json was refreshed from GitHub a moment ago")
    else:
        notes.append("not compared with GitHub (add --live, or run `update`)")

    for p in passed:
        print(f"ok    {p}")
    for n in notes:
        print(f"note  {n}")
    for f in fails:
        print(f"FAIL  {f}")
    _say_pending(pending, ci)
    return 1 if fails else NEEDS_WORDS if pending else 0


def cmd_update(ci: bool) -> int:
    pending = cmd_refresh(False, ci)
    code = cmd_build() or cmd_check(False, ci, just_refreshed=True)
    return code or (NEEDS_WORDS if pending else 0)


def cmd_preview() -> int:
    rendered = build.render_all(ROOT)
    if build.drift(ROOT, rendered):
        print("FAIL  the page on disk is not current: run `build` first", file=sys.stderr)
        return 1
    catalog = _catalog()
    css_light, css_dark = live.markdown_css()
    html = preview.page(
        (ROOT / "templates" / "preview.html").read_text(encoding="utf-8"),
        live.render_markdown(ROOT / build.README, catalog.org),
        {rel.removeprefix("profile/"): text for rel, text in rendered.items() if rel.endswith(".svg")},
        css_light, css_dark, live.org_avatar(catalog.org), catalog.org, catalog.community_name.removeprefix("The "),
        art.HEADER_ALT, "profile preview",
    )
    _write(PREVIEW, html)
    print(f"wrote {PREVIEW}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="profilegen", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("update").add_argument("--ci", action="store_true")
    sub.add_parser("sync").add_argument("--dry-run", action="store_true")
    r = sub.add_parser("refresh")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--ci", action="store_true")
    sub.add_parser("build")
    c = sub.add_parser("check")
    c.add_argument("--live", action="store_true")
    c.add_argument("--ci", action="store_true")
    sub.add_parser("preview")
    args = p.parse_args(argv)
    try:
        if args.cmd == "sync":
            return cmd_sync(args.dry_run)
        if args.cmd == "refresh":
            return NEEDS_WORDS if cmd_refresh(args.dry_run, args.ci) else 0
        if args.cmd == "build":
            return cmd_build()
        if args.cmd == "check":
            return cmd_check(args.live, args.ci)
        if args.cmd == "preview":
            return cmd_preview()
        return cmd_update(args.ci)
    except (live.GhError, preview.PreviewError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except (CatalogError, TemplateError) as e:
        print(f"FAIL  {e}", file=sys.stderr)
        return 1
