"""profile/README.md from the template, the catalog and the org snapshot. Pure."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from html import escape

from .art import MOTIFS
from .catalog import Catalog, Entry, RepoFacts, Snapshot

COVER_WIDTH = 280
LATEST_RELEASES = 6
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class TemplateError(Exception):
    """The template names a block nothing fills, or leaves a placeholder behind."""


@dataclass(frozen=True)
class Item:
    entry: Entry
    facts: RepoFacts

    @property
    def status(self) -> str:
        if self.facts.empty:
            return "soon"
        return "released" if self.facts.releases else "unreleased"


def items(catalog: Catalog, snapshot: Snapshot) -> list[Item]:
    """Every repo the page shows. With on_the_way.show off, repos with no commits yet are
    left out entirely: no section, no cover, no count."""
    its = [Item(catalog.entries[name], snapshot.repos[name]) for name in sorted(snapshot.repos)]
    return its if catalog.on_the_way.show else [i for i in its if i.status != "soon"]


def date(iso: str) -> str:
    """Month names spelled out by hand: strftime's %b follows the machine's locale."""
    d = datetime.strptime(iso[:10], "%Y-%m-%d")
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def fill(template: str, blocks: dict[str, str]) -> str:
    def sub(m: re.Match) -> str:
        if m.group(1) not in blocks:
            raise TemplateError(f"template placeholder {{{{{m.group(1)}}}}} has no block (known: {', '.join(sorted(blocks))})")
        return blocks[m.group(1)]

    out = PLACEHOLDER.sub(sub, template)
    if "{{" in out or "}}" in out:
        raise TemplateError("a placeholder is left unfilled or malformed in the rendered README")
    return out


# ── blocks ───────────────────────────────────────────────────────────────────

def header_block(alt: str) -> str:
    """Never wrap this <picture> in a link: GitHub wraps the <img> in its own link, and
    the nested anchor makes its renderer pull the <img> out of the <picture>, so the
    light/dark swap silently stops working."""
    return "\n".join([
        "<picture>",
        '  <source media="(prefers-color-scheme: dark)" srcset="./assets/header-dark.svg">',
        '  <source media="(prefers-color-scheme: light)" srcset="./assets/header-light.svg">',
        f'  <img src="./assets/header-dark.svg" width="100%" alt="{_q(alt)}">',
        "</picture>",
    ])


def buttons_block(catalog: Catalog) -> str:
    return "\n".join(f'  <a href="{_q(b.url)}"><img src="./assets/buttons/{slug(b.label)}.svg" height="36" alt="{_q(b.label)}"></a>'
                     for b in catalog.buttons)


def _q(value: str) -> str:
    """Safe inside a double-quoted HTML attribute."""
    return escape(value, quote=True)


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def summary_block(its: list[Item]) -> str:
    open_ = [i for i in its if i.status != "soon"]
    soon = [i for i in its if i.status == "soon"]
    head = f"{_count(len(open_), 'repository', 'repositories')} open to members today"
    if soon:
        head += f", {len(soon)} on the way"
    line = f"**{head}.**"
    released = [(i, i.facts.releases[0]) for i in its if i.facts.releases]
    if released:
        item, rel = max(released, key=lambda p: p[1].published)
        line += f" Latest release: [{item.entry.name} {rel.tag}]({rel.url}), {date(rel.published)}."
    return line


def _row(item: Item, catalog: Catalog) -> str:
    e, f = item.entry, item.facts
    tier = catalog.tiers[f.tier]
    if item.status == "soon":
        state = "on the way"
    elif item.status == "unreleased":
        state = "no release yet"
    else:
        state = f"**{f.releases[0].tag}** · {date(f.releases[0].published)}"
    meta = [f"<code>{e.repo}</code>", state]
    if tier.on_cards:
        meta.append(f"**{tier.label}**" if f.tier == "premium" else tier.label)
    lines = [
        "<tr>",
        f'<td width="{COVER_WIDTH + 10}" valign="top"><a href="{_q(f.url)}"><img src="./assets/covers/{e.repo}.svg" '
        f'width="{COVER_WIDTH}" alt="{_q(e.name)} cover: {MOTIFS[e.motif]}"></a></td>',
        '<td valign="top">',
        "",
        f"**[{e.name}]({f.url})**<br>",
        f"<sub>{' · '.join(meta)}</sub>",
        "",
        e.pitch,
    ]
    if catalog.show_stack and e.stack:
        lines += ["", f"<sub>{' · '.join(e.stack)}</sub>"]
    for link in e.links:
        lines += ["", f"[{link.label} →]({link.url})"]
    lines += ["", "</td>", "</tr>"]
    return "\n".join(lines)


def _tables(rows: list[Item], catalog: Catalog) -> str:
    """One table per repository: GitHub shades every second row of a table, which would
    tint every other card."""
    return "\n\n".join(f"<table>\n{_row(i, catalog)}\n</table>" for i in rows)


def catalog_block(its: list[Item], catalog: Catalog) -> str:
    out = []
    # Explain the tier names that appear on cards, and only those.
    used = sorted({i.facts.tier for i in its if catalog.tiers[i.facts.tier].on_cards},
                  key=lambda t: list(catalog.tiers).index(t))
    if used:
        legend = " · ".join(f"**{catalog.tiers[t].label}**: {catalog.tiers[t].note}" for t in used)
        out += [f"<sub>{legend}</sub>", ""]
    for cat in catalog.categories:
        rows = [i for i in its if i.entry.category == cat.id and i.status != "soon"]
        if not rows:
            continue
        out += [f"### {cat.title}", ""]
        if cat.intro:
            out += [cat.intro, ""]
        out += [_tables(rows, catalog), ""]
    soon = [i for i in its if i.status == "soon"]
    if soon:
        order = [c.id for c in catalog.categories]
        soon.sort(key=lambda i: (order.index(i.entry.category), i.entry.name))
        out += [f"### {catalog.on_the_way.title}", ""]
        if catalog.on_the_way.intro:
            out += [catalog.on_the_way.intro, ""]
        out += [_tables(soon, catalog), ""]
    if not its:
        out += ["Nothing is released yet. The first repositories are on the way.", ""]
    return "\n".join(out).rstrip()


def releases_block(its: list[Item]) -> str:
    all_releases = sorted(((r, i) for i in its for r in i.facts.releases), key=lambda p: p[0].published, reverse=True)
    if not all_releases:
        return "No releases yet. The first ones are on the way."
    lines = ["| Date | Repository | Release |", "|:--|:--|:--|"]
    for rel, item in all_releases[:LATEST_RELEASES]:
        lines.append(f"| {date(rel.published)} | {item.entry.name} | [{rel.tag}]({rel.url}) |")
    return "\n".join(lines)


def render(template: str, catalog: Catalog, snapshot: Snapshot, header_alt: str) -> str:
    its = items(catalog, snapshot)
    return fill(template, {
        "header": header_block(header_alt),
        "buttons": buttons_block(catalog),
        "community_name": catalog.community_name,
        "community_url": catalog.community_url,
        "summary": summary_block(its),
        "catalog": catalog_block(its, catalog),
        "releases": releases_block(its),
    })
