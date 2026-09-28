"""Everything that reaches outside this repository: the gh CLI, git, the sibling clones
and the private release config in ~/.claude/release. The only module allowed to.

Read-only toward GitHub: it lists repos, teams and releases, clones or fast-forwards,
and asks GitHub's Markdown API to render the README for a preview (that call stores
nothing). It never pushes, never edits a checkout with local changes, and never writes
anything to GitHub. Publishing is git's job, and a human's (or the autopilot's) call.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

RELEASE_CONFIG = Path(os.environ.get("RELEASE_CONFIG", "~/.claude/release/config.json")).expanduser()
PROFILE_REPOS = {".github", ".github-private"}  # the profile itself is not a product
KEEP_RELEASES = 5
MARKDOWN_CSS = "https://cdn.jsdelivr.net/npm/github-markdown-css@5.8.1/github-markdown-{}.css"


class GhError(Exception):
    """gh or git failed, or the release config needed to read tiers is missing."""


def _run(args: list[str], cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    except FileNotFoundError as e:
        raise GhError(f"`{args[0]}` is not installed or not on PATH") from e
    except subprocess.TimeoutExpired as e:
        raise GhError(f"`{args[0]} {args[1] if len(args) > 1 else ''}` took longer than {timeout}s") from e


def gh_api(path: str, allow_empty_repo: bool = False):
    r = _run(["gh", "api", "-H", "Accept: application/vnd.github+json", path])
    if r.returncode != 0:
        if allow_empty_repo and "Git Repository is empty" in (r.stdout + r.stderr):
            return None
        raise GhError(f"gh api {path} failed: {(r.stderr or r.stdout).strip()[:300]}")
    return json.loads(r.stdout or "null")


def gh_api_all(path: str) -> list:
    sep = "&" if "?" in path else "?"
    out, page = [], 1
    while True:
        chunk = gh_api(f"{path}{sep}per_page=100&page={page}")
        out += chunk
        if len(chunk) < 100:
            return out
        page += 1


def release_config() -> dict:
    """The tier map. In the autopilot it comes from the PROFILE_TIERS secret (JSON of the
    `tiers` map), because the release config never leaves Marvin's machine."""
    env = os.environ.get("PROFILE_TIERS")
    if env:
        try:
            return {"tiers": json.loads(env)}
        except ValueError as e:
            raise GhError("PROFILE_TIERS is not valid JSON") from e
    try:
        return json.loads(RELEASE_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise GhError(f"cannot read {RELEASE_CONFIG} (tiers come from its `tiers` map): {e}") from e


def denylist_text() -> str | None:
    """The private deny-list, or None when this machine has none (CI)."""
    try:
        path = Path(release_config().get("denylist", "~/.claude/release/denylist.txt")).expanduser()
    except GhError:
        path = Path("~/.claude/release/denylist.txt").expanduser()
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def tier_of(teams: set[str], visibility: str, tiers: dict[str, list[str]]) -> str | None:
    """The widest audience whose teams all have read access. Public repos are public."""
    if visibility == "public":
        return "public"
    fitting = [t for t, needed in tiers.items() if needed and set(needed) <= teams]
    return max(fitting, key=lambda t: len(tiers[t])) if fitting else None


TAG = re.compile(r"v?\d+(\.\d+){1,3}([-+][0-9A-Za-z.-]+)?")
ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def fetch_snapshot(org: str, listed: set[str], redact: bool = False) -> tuple[dict, list[str], list[str]]:
    """The org as members see it: (snapshot, pending, notes).

    Only repos with a catalog entry (`listed`) enter the snapshot, which is public. A
    repo members can read but the catalog does not list yet is returned in `pending`,
    so nothing unreviewed ever reaches the page. Team slugs derive the tier and are
    dropped. Only machine facts are kept (tier, empty, tag, date, link), each checked
    for shape, so no free text from GitHub reaches the page.

    redact=True is for public logs (the autopilot): notes and errors never name a repo
    that is not in the catalog.
    """
    tiers = release_config().get("tiers") or {}
    if not tiers:
        raise GhError("the tier map is empty (release config `tiers`, or PROFILE_TIERS)")

    def called(name: str) -> str:
        return name if name in listed or not redact else "an unlisted repository"

    repos, pending, notes = [], [], []
    for r in sorted(gh_api_all(f"orgs/{org}/repos?type=all"), key=lambda r: r["name"]):
        name = r["name"]
        if name in PROFILE_REPOS:
            continue
        if r.get("archived"):
            notes.append(f"{called(name)}: archived, left out")
            continue
        try:
            teams = {t["slug"] for t in gh_api_all(f"repos/{org}/{name}/teams")}
        except GhError:
            if redact and name not in listed:
                raise GhError("could not read the team access of an unlisted repository (token permissions?)") from None
            raise
        tier = tier_of(teams, r.get("visibility", "private"), tiers)
        if tier is None:
            notes.append(f"{called(name)}: no member tier can read it, left out")
            continue
        if name not in listed:
            pending.append(name)
            continue
        empty = gh_api(f"repos/{org}/{name}/commits?per_page=1", allow_empty_repo=True) in (None, [])
        releases, prefix = [], f"https://github.com/{org}/{name}/releases/"
        # 100 per page, so a run of prereleases cannot push every stable release off the page
        for x in [] if empty else gh_api(f"repos/{org}/{name}/releases?per_page=100"):
            if x.get("draft") or x.get("prerelease") or not x.get("published_at"):
                continue
            if not (TAG.fullmatch(x.get("tag_name", "")) and ISO.fullmatch(x["published_at"])
                    and str(x.get("html_url", "")).startswith(prefix)):
                notes.append(f"{name}: a release with an unexpected tag, date or link was left out")
                continue
            releases.append({"tag": x["tag_name"], "published": x["published_at"], "url": x["html_url"]})
        releases.sort(key=lambda x: x["published"], reverse=True)
        repos.append({
            "name": name,
            "tier": tier,
            "empty": empty,
            "url": f"https://github.com/{org}/{name}",
            "releases": releases[:KEEP_RELEASES],
        })
    return {"org": org, "repos": repos}, pending, notes


# ── the workspace: one clone per org repo, next to this one ─────────────────

def _same_repo(url: str, org: str, name: str) -> bool:
    """Exactly github.com/<org>/<name>: `agentic-seo-system` must not match `...-app`."""
    return re.search(rf"github\.com[:/]{re.escape(org)}/{re.escape(name)}(\.git)?/?$", url, re.I) is not None


def _git(cwd: Path, *args: str) -> str:
    r = _run(["git", *args], cwd=cwd)
    if r.returncode != 0:
        raise GhError(f"git {' '.join(args)} in {cwd.name}: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout.strip()


def sync(org: str, workspace: Path, dry_run: bool) -> list[str]:
    """Clone every org repo missing from the workspace; fast-forward the clean ones.

    A checkout with local changes, on another branch, or pointing elsewhere is left
    alone and reported. Nothing is ever pushed, reset or forced.
    """
    report = []
    org_repos = sorted(gh_api_all(f"orgs/{org}/repos?type=all"), key=lambda r: r["name"])
    for r in org_repos:
        name = r["name"]
        if name in PROFILE_REPOS or r.get("archived"):
            continue
        dest = workspace / name
        default = r.get("default_branch") or "main"
        if not dest.exists():
            report.append(f"clone  {name}")
            if not dry_run:
                try:
                    res = _run(["gh", "repo", "clone", f"{org}/{name}", str(dest), "--", "--quiet"], timeout=600)
                    ok, msg = res.returncode == 0, (res.stderr or res.stdout).strip()[:200]
                except GhError as e:
                    ok, msg = False, f"{e}; delete the half-cloned folder {dest.name} and run sync again"
                if not ok:
                    report[-1] = f"FAILED clone {name}: {msg}"
            continue
        if not (dest / ".git").exists():
            report.append(f"skip   {name}: folder exists but is not a git clone")
            continue
        origin = _run(["git", "remote", "get-url", "origin"], cwd=dest)
        if origin.returncode != 0 or not _same_repo(origin.stdout.strip(), org, name):
            report.append(f"skip   {name}: its origin is not github.com/{org}/{name}")
            continue
        if _git(dest, "status", "--porcelain"):
            report.append(f"skip   {name}: has local changes (these clones are read-only mirrors)")
            continue
        unborn = _run(["git", "rev-parse", "--verify", "--quiet", "HEAD"], cwd=dest).returncode != 0
        branch = default if unborn else _git(dest, "rev-parse", "--abbrev-ref", "HEAD")
        if branch != default:
            report.append(f"skip   {name}: on branch {branch}, not {default}")
            continue
        report.append(f"pull   {name}")
        if not dry_run:
            # A clone of an empty repo tracks nothing yet, so name the branch explicitly.
            res = _run(["git", "pull", "--ff-only", "--quiet", "origin", default], cwd=dest, timeout=600)
            if res.returncode != 0:
                msg = (res.stderr or res.stdout).strip()
                report[-1] = (f"empty  {name}: nothing released yet" if unborn and "couldn't find remote ref" in msg
                              else f"FAILED pull {name}: {msg[:200]}")
    known = {r["name"] for r in org_repos} | PROFILE_REPOS
    for p in sorted(workspace.iterdir()):
        if p.is_dir() and not p.name.startswith(".") and p.name not in known:
            report.append(f"note   {p.name}: in the workspace but not in the org")
    return report


def committable_files(root: Path) -> dict[str, bytes]:
    """Every file git would let you commit here: tracked plus untracked-not-ignored."""
    listed = _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    files = {}
    for rel in sorted(set(filter(None, listed.split("\0")))):
        p = root / rel
        if p.is_file():
            files[rel] = p.read_bytes()
    return files


# ── preview: the page as GitHub will render it ──────────────────────────────

def render_markdown(readme: Path, org: str) -> str:
    """GitHub's own renderer, in README mode, with the profile repo as context."""
    r = _run(["gh", "api", "-X", "POST", "markdown", "-f", "mode=markdown",
              "-f", f"context={org}/.github", "-F", f"text=@{readme}"])
    if r.returncode != 0:
        raise GhError(f"GitHub's markdown API failed: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout


def fetch_url(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 (fixed https hosts)
            return resp.read()
    except OSError as e:
        raise GhError(f"could not download {url}: {e}") from e


def markdown_css() -> tuple[str, str]:
    return tuple(fetch_url(MARKDOWN_CSS.format(v)).decode("utf-8") for v in ("light", "dark"))


def org_avatar(org: str) -> bytes:
    return fetch_url(gh_api(f"orgs/{org}")["avatar_url"] + "&s=120")
