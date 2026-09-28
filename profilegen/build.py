"""Everything `build` writes, as a pure function of the files in this repository.

Inputs: catalog.yaml, data/org.json, templates/README.md.tmpl, fonts/.
Output: {repo-relative path: file content}. `build` writes it; `check` compares it.
No network, no sibling clones: that is what lets CI prove the page is current.
"""
from __future__ import annotations

from pathlib import Path

from . import art, readme
from .catalog import CatalogError, load_catalog, load_snapshot, reconcile

CATALOG = "catalog.yaml"
SNAPSHOT = "data/org.json"
TEMPLATE = "templates/README.md.tmpl"
README = "profile/README.md"
# build owns this folder completely: any file in it that build did not produce is stale.
MANAGED = "profile"


def _tag(status: str, tier: str, label: str, on_cards: bool) -> tuple[str | None, str]:
    """The corner tag of a cover: none when the card names no tier."""
    if status == "soon":
        return "ON THE WAY", "soon"
    if not on_cards:
        return None, "none"
    return label.upper(), "solid" if tier == "premium" else "outline"


def render_all(root: Path) -> dict[str, str]:
    catalog = load_catalog(root / CATALOG, set(art.MOTIFS))
    snapshot = load_snapshot(root / SNAPSHOT)
    reconcile(catalog, snapshot)

    out = {
        "profile/assets/header-dark.svg": art.header("dark"),
        "profile/assets/header-light.svg": art.header("light"),
    }
    for item in readme.items(catalog, snapshot):
        e, f = item.entry, item.facts
        tier = catalog.tiers[f.tier]
        tag, style = _tag(item.status, f.tier, tier.label, tier.on_cards)
        try:
            out[f"profile/assets/covers/{e.repo}.svg"] = art.cover(e.repo, e.name, e.kicker, e.motif, tag, style)
        except art.DoesNotFit as err:
            raise CatalogError(f"repos.{e.repo}: {err}") from err
    for b in catalog.buttons:
        out[f"profile/assets/buttons/{readme.slug(b.label)}.svg"] = art.button(b.label, b.style)

    template = (root / TEMPLATE).read_text(encoding="utf-8")
    out[README] = readme.render(template, catalog, snapshot, art.HEADER_ALT)
    return dict(sorted(out.items()))


def stale_files(root: Path, rendered: dict[str, str]) -> list[str]:
    """Files anywhere under profile/ that the current build would not produce."""
    folder = root / MANAGED
    found = [p.relative_to(root).as_posix() for p in sorted(folder.rglob("*")) if p.is_file()] if folder.is_dir() else []
    return sorted(f for f in found if f not in rendered)


def drift(root: Path, rendered: dict[str, str]) -> list[str]:
    """Paths whose bytes on disk differ from a fresh build (missing counts as different)."""
    changed = []
    for rel, content in rendered.items():
        p = root / rel
        if not p.exists() or p.read_bytes() != content.encode("utf-8"):
            changed.append(rel)
    return changed
