"""Load and validate the two inputs of every build.

- catalog.yaml   hand-written words: names, pitches, sections, buttons
- data/org.json  facts fetched from GitHub by `refresh`: repos, tiers, releases

Pure: reads the files it is handed. Never the network, never the sibling clones.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

TIERS = ("standard", "premium", "public")
BUTTON_STYLES = ("primary", "secondary")
# Marvin's voice, enforced: none of these words, and no version numbers (GitHub owns those).
BANNED_WORDS = ("game-changer", "game changer", "unlock", "leverage", "empower", "supercharge",
                "revolutionize", "revolutionise", "seamless", "robust", "cutting-edge", "cutting edge")
PITCH_MAX = 150  # a card pitch reads in one breath
VERSION = re.compile(r"\bv?\d+\.\d+(\.\d+)?\b")
URL = re.compile(r"https://[^\s\"'<>]+")


class CatalogError(Exception):
    """catalog.yaml is malformed, or it and the org disagree."""


@dataclass(frozen=True)
class Link:
    label: str
    url: str


@dataclass(frozen=True)
class Button:
    label: str
    url: str
    style: str


@dataclass(frozen=True)
class Tier:
    label: str
    note: str
    on_cards: bool  # name this tier on each card and its cover


@dataclass(frozen=True)
class Category:
    id: str
    title: str
    intro: str


@dataclass(frozen=True)
class Entry:
    repo: str
    name: str
    category: str
    kicker: str
    motif: str
    pitch: str
    stack: tuple[str, ...]
    links: tuple[Link, ...]


@dataclass(frozen=True)
class OnTheWay:
    """Repos with no commits yet: a teaser section, or nothing at all."""
    show: bool
    title: str
    intro: str


@dataclass(frozen=True)
class Catalog:
    org: str
    community_name: str
    community_url: str
    buttons: tuple[Button, ...]
    tiers: dict[str, Tier]
    categories: tuple[Category, ...]
    entries: dict[str, Entry]
    on_the_way: OnTheWay
    show_stack: bool  # the technology line under each pitch


@dataclass(frozen=True)
class Release:
    tag: str
    published: str  # ISO 8601, UTC
    url: str


@dataclass(frozen=True)
class RepoFacts:
    name: str
    tier: str
    empty: bool
    url: str
    releases: tuple[Release, ...]  # newest first


@dataclass(frozen=True)
class Snapshot:
    org: str
    repos: dict[str, RepoFacts]


def _need(d: dict, key: str, where: str, kind: type = str):
    if key not in d or d[key] in (None, ""):
        raise CatalogError(f"{where}: `{key}` is missing")
    if not isinstance(d[key], kind):
        raise CatalogError(f"{where}: `{key}` must be a {kind.__name__}")
    return d[key]


def _only(d: dict, allowed: set[str], where: str) -> None:
    extra = sorted(set(d) - allowed)
    if extra:
        raise CatalogError(f"{where}: unknown key(s) {', '.join(extra)}")


def _url(value: str, where: str) -> str:
    if not URL.fullmatch(value):
        raise CatalogError(f"{where}: `{value}` is not an https link")
    return value


def _voice(pitch: str, where: str) -> None:
    if len(pitch) > PITCH_MAX:
        raise CatalogError(f"{where}: the pitch has {len(pitch)} characters; keep it to {PITCH_MAX}")
    low = pitch.lower()
    hits = [w for w in BANNED_WORDS if w in low]
    if hits:
        raise CatalogError(f"{where}: the pitch uses {', '.join(hits)}; say what it does instead")
    if VERSION.search(pitch):
        raise CatalogError(f"{where}: the pitch names a version; versions come from GitHub and would go stale")


def load_catalog(path: Path, motifs: set[str]) -> Catalog:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise CatalogError(f"{path.name}: not valid YAML ({e})") from e
    _only(raw, {"org", "community", "buttons", "tiers", "cards", "on_the_way", "categories", "repos"}, path.name)
    community = _need(raw, "community", path.name, dict)
    _only(community, {"name", "url"}, "community")

    buttons = []
    for i, b in enumerate(raw.get("buttons") or []):
        where = f"buttons[{i}]"
        _only(b, {"label", "url", "style"}, where)
        style = _need(b, "style", where)
        if style not in BUTTON_STYLES:
            raise CatalogError(f"{where}: style must be one of {', '.join(BUTTON_STYLES)}")
        buttons.append(Button(_need(b, "label", where), _url(_need(b, "url", where), where), style))

    tiers = {}
    for tid, t in (_need(raw, "tiers", path.name, dict)).items():
        if tid not in TIERS:
            raise CatalogError(f"tiers.{tid}: unknown tier (known: {', '.join(TIERS)})")
        _only(t, {"label", "note", "on_cards"}, f"tiers.{tid}")
        tiers[tid] = Tier(_need(t, "label", f"tiers.{tid}"), _need(t, "note", f"tiers.{tid}"),
                          _need(t, "on_cards", f"tiers.{tid}", bool))

    categories = []
    for i, c in enumerate(_need(raw, "categories", path.name, list)):
        where = f"categories[{i}]"
        _only(c, {"id", "title", "intro"}, where)
        categories.append(Category(_need(c, "id", where), _need(c, "title", where), c.get("intro", "")))
    cat_ids = {c.id for c in categories}
    if len(cat_ids) != len(categories):
        raise CatalogError("categories: duplicate id")

    entries = {}
    for repo, e in (_need(raw, "repos", path.name, dict)).items():
        where = f"repos.{repo}"
        _only(e, {"name", "category", "kicker", "motif", "pitch", "stack", "links"}, where)
        category = _need(e, "category", where)
        if category not in cat_ids:
            raise CatalogError(f"{where}: category `{category}` is not in categories")
        motif = _need(e, "motif", where)
        if motif not in motifs:
            raise CatalogError(f"{where}: motif `{motif}` is not one of {', '.join(sorted(motifs))}")
        links = []
        for lk in e.get("links") or []:
            _only(lk, {"label", "url"}, f"{where}.links")
            links.append(Link(_need(lk, "label", f"{where}.links"), _url(_need(lk, "url", f"{where}.links"), where)))
        stack = e.get("stack") or []
        if not isinstance(stack, list) or not all(isinstance(x, str) and x for x in stack):
            raise CatalogError(f"{where}: `stack` must be a list of names, like [Python, Docker]")
        pitch = " ".join(_need(e, "pitch", where).split())
        _voice(pitch, where)
        entries[repo] = Entry(repo, _need(e, "name", where), category, _need(e, "kicker", where), motif,
                              pitch, tuple(stack), tuple(links))

    cards = _need(raw, "cards", path.name, dict)
    _only(cards, {"stack"}, "cards")
    show_stack = _need(cards, "stack", "cards", bool)

    otw = _need(raw, "on_the_way", path.name, dict)
    _only(otw, {"show", "title", "intro"}, "on_the_way")
    on_the_way = OnTheWay(_need(otw, "show", "on_the_way", bool), _need(otw, "title", "on_the_way"),
                          otw.get("intro", ""))

    return Catalog(_need(raw, "org", path.name), _need(community, "name", "community"),
                   _need(community, "url", "community"), tuple(buttons), tiers, tuple(categories), entries,
                   on_the_way, show_stack)


def load_snapshot(path: Path) -> Snapshot:
    if not path.exists():
        raise CatalogError(f"{path.as_posix()} does not exist yet: run `refresh` first")
    raw = json.loads(path.read_text(encoding="utf-8"))
    repos = {
        r["name"]: RepoFacts(r["name"], r["tier"], r["empty"], r["url"],
                             tuple(Release(x["tag"], x["published"], x["url"]) for x in r["releases"]))
        for r in raw["repos"]
    }
    return Snapshot(raw["org"], repos)


def reconcile(catalog: Catalog, snapshot: Snapshot) -> None:
    """Can this snapshot be rendered with this catalog? `refresh` only writes repos that
    have an entry, so a failure here means one of the two files was edited by hand."""
    problems = []
    if catalog.org != snapshot.org:
        problems.append(f"catalog.yaml is for `{catalog.org}` but data/org.json is for `{snapshot.org}`")
    for name in sorted(set(snapshot.repos) - set(catalog.entries)):
        problems.append(f"`{name}` is in data/org.json but has no entry in catalog.yaml "
                        f"(write one from ../{name}/README.md, then run `update`)")
    for name, facts in sorted(snapshot.repos.items()):
        if facts.tier not in catalog.tiers:
            problems.append(f"`{name}` has tier `{facts.tier}`, which catalog.yaml has no label for")
    if problems:
        raise CatalogError("\n".join(problems))


def unshown(catalog: Catalog, snapshot: Snapshot) -> list[str]:
    """Entries the page leaves out because members cannot see that repo (yet): renamed,
    deleted, archived, or created but not released to a tier. Showing less is safe."""
    return sorted(set(catalog.entries) - set(snapshot.repos))
