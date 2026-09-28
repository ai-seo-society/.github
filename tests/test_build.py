"""The page is generated from catalog.yaml + data/org.json, and the gates hold."""
import json
import shutil
from pathlib import Path

import pytest
import yaml

from profilegen import art, build, readme
from profilegen.catalog import CatalogError, load_catalog, load_snapshot, unshown

ROOT = Path(__file__).resolve().parent.parent


def _release(name, tag, when):
    return {"tag": tag, "published": when, "url": f"https://github.com/ai-seo-society/{name}/releases/tag/{tag}"}


def _repo(name, tier="standard", empty=False, releases=()):
    return {"name": name, "tier": tier, "empty": empty,
            "url": f"https://github.com/ai-seo-society/{name}", "releases": list(releases)}


@pytest.fixture
def site(tmp_path):
    """A copy of this repo's inputs with a small, invented org."""
    (tmp_path / build.TEMPLATE).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / build.TEMPLATE, tmp_path / build.TEMPLATE)
    catalog = yaml.safe_load((ROOT / build.CATALOG).read_text(encoding="utf-8"))
    catalog["on_the_way"]["show"] = True
    catalog["repos"] = {
        "alpha": {"name": "Alpha Tool", "category": "tools", "kicker": "CLI", "motif": "terminal",
                  "pitch": "Does one | thing well.", "stack": ["Python"]},
        "beta": {"name": "Beta App", "category": "apps", "kicker": "App", "motif": "dashboard",
                 "pitch": "An app.", "links": [{"label": "Demo", "url": "https://example.com"}]},
        "gamma": {"name": "Gamma", "category": "systems", "kicker": "System", "motif": "rank", "pitch": "Soon."},
    }
    _save_catalog(tmp_path, catalog)
    snapshot = {"org": "ai-seo-society", "repos": [
        _repo("alpha", releases=[_release("alpha", "v1.2.0", "2026-03-04T10:00:00Z"),
                                 _release("alpha", "v1.1.0", "2026-02-01T10:00:00Z")]),
        _repo("beta", tier="premium", releases=[_release("beta", "v0.9.0", "2026-05-06T10:00:00Z")]),
        _repo("gamma", empty=True),
    ]}
    (tmp_path / "data").mkdir()
    _save(tmp_path, snapshot)
    return tmp_path


def _catalog_raw(site):
    return yaml.safe_load((site / build.CATALOG).read_text(encoding="utf-8"))


def _save_catalog(site, raw):
    (site / build.CATALOG).write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def _snapshot(site):
    return json.loads((site / build.SNAPSHOT).read_text(encoding="utf-8"))


def _save(site, snap):
    (site / build.SNAPSHOT).write_text(json.dumps(snap), encoding="utf-8")


def _write_all(site, rendered):
    for rel, text in rendered.items():
        (site / rel).parent.mkdir(parents=True, exist_ok=True)
        (site / rel).write_text(text, encoding="utf-8", newline="\n")


def test_the_committed_page_is_current():
    rendered = build.render_all(ROOT)
    assert build.drift(ROOT, rendered) == [], "run `uv run python -m profilegen build` and commit"
    assert build.stale_files(ROOT, rendered) == []


def test_build_is_deterministic(site):
    assert build.render_all(site) == build.render_all(site)


def test_page_lists_every_repo_with_its_facts(site):
    page = build.render_all(site)[build.README]
    assert "**v1.2.0** · 4 Mar 2026" in page
    assert "<code>alpha</code>" in page
    assert "**Premium**" in page
    assert "### On the way" in page and page.index("### On the way") < page.index("Gamma")
    assert "[Demo →](https://example.com)" in page


def test_one_table_per_repo_so_github_does_not_shade_every_other_card(site):
    page = build.render_all(site)[build.README]
    body = page.split("## What is inside")[1].split("## Latest releases")[0]
    assert body.count("<table>") == 3 and body.count("<tr>") == 3


def test_attribute_values_are_escaped(site):
    raw = _catalog_raw(site)
    raw["repos"]["alpha"]["name"] = 'Alpha "Tool"'
    _save_catalog(site, raw)
    page = build.render_all(site)[build.README]
    assert 'alt="Alpha &quot;Tool&quot; cover' in page


def test_latest_releases_are_newest_first(site):
    block = build.render_all(site)[build.README].split("## Latest releases")[1].split("##")[0]
    assert block.index("v0.9.0") < block.index("v1.2.0") < block.index("v1.1.0")


def test_covers_follow_tier_and_status(site):
    out = build.render_all(site)
    assert {k for k in out if "/covers/" in k} == {f"profile/assets/covers/{n}.svg" for n in ("alpha", "beta", "gamma")}
    assert 'opacity="0.42"' in out["profile/assets/covers/gamma.svg"]  # dimmed: on the way


def test_snapshot_repo_without_entry_fails(site):
    """refresh never writes such a repo; this only happens when a file was edited by hand."""
    snap = _snapshot(site)
    snap["repos"].append(_repo("delta"))
    _save(site, snap)
    with pytest.raises(CatalogError, match="`delta` is in data/org.json but has no entry"):
        build.render_all(site)


def test_entry_whose_repo_members_cannot_see_is_left_out(site):
    """Showing less is the safe direction: renamed, deleted, or not released to a tier yet."""
    snap = _snapshot(site)
    snap["repos"] = [r for r in snap["repos"] if r["name"] != "beta"]
    _save(site, snap)
    out = build.render_all(site)
    assert "Beta App" not in out[build.README]
    assert "profile/assets/covers/beta.svg" not in out
    catalog = load_catalog(site / build.CATALOG, set(art.MOTIFS))
    assert unshown(catalog, load_snapshot(site / build.SNAPSHOT)) == ["beta"]


@pytest.mark.parametrize("field, value, message", [
    ("motif", "hologram", "motif `hologram`"),
    ("category", "nowhere", "category `nowhere`"),
    ("version", "1.0", "unknown key"),                      # versions come from GitHub, never from here
    ("stack", "Python", "must be a list"),                   # a string would render as P · y · t · h · o · n
    ("pitch", "A robust tool that runs daily.", "uses robust"),
    ("pitch", "New in 2.4: faster scans.", "names a version"),
    ("links", [{"label": "Demo", "url": "javascript:alert(1)"}], "not an https link"),
])
def test_catalog_rejects_bad_entries(site, field, value, message):
    raw = _catalog_raw(site)
    raw["repos"]["alpha"][field] = value
    _save_catalog(site, raw)
    with pytest.raises(CatalogError, match=message):
        load_catalog(site / build.CATALOG, set(art.MOTIFS))


def test_catalog_rejects_unknown_keys_in_every_section(site):
    raw = _catalog_raw(site)
    raw["tiers"]["premium"]["price"] = "99"
    _save_catalog(site, raw)
    with pytest.raises(CatalogError, match="tiers.premium: unknown key"):
        load_catalog(site / build.CATALOG, set(art.MOTIFS))


def test_a_kicker_that_does_not_fit_fails_the_build(site):
    raw = _catalog_raw(site)
    raw["repos"]["alpha"]["kicker"] = "A command line tool for everything you need"
    _save_catalog(site, raw)
    with pytest.raises(CatalogError, match="repos.alpha: kicker"):
        build.render_all(site)


def test_template_placeholders_must_be_known():
    with pytest.raises(readme.TemplateError, match="nope"):
        readme.fill("a {{nope}} b", {"x": "1"})
    assert readme.fill("a {{ x }} b", {"x": "1"}) == "a 1 b"


def test_any_file_under_profile_that_build_did_not_make_is_stale(site):
    rendered = build.render_all(site)
    _write_all(site, rendered)
    for extra in ("profile/assets/covers/old.svg", "profile/assets/header-old.svg", "profile/notes.md",
                  "profile/assets/covers/old/x.svg"):
        (site / extra).parent.mkdir(parents=True, exist_ok=True)
        (site / extra).write_text("x", encoding="utf-8")
    assert build.stale_files(site, rendered) == sorted([
        "profile/assets/covers/old.svg", "profile/assets/covers/old/x.svg",
        "profile/assets/header-old.svg", "profile/notes.md"])
    assert build.drift(site, rendered) == []


def test_header_picture_is_not_inside_a_link(site):
    """GitHub's renderer breaks <picture> inside <a>: the dark header would show in light mode."""
    page = build.render_all(site)[build.README]
    before = page[: page.index("<picture>")]
    assert before.count("<a ") == before.count("</a>")


def test_dates_ignore_the_machine_locale():
    assert readme.date("2026-09-28T14:45:56Z") == "28 Sep 2026"


def test_on_the_way_can_be_switched_off_entirely(site):
    raw = _catalog_raw(site)
    raw["on_the_way"]["show"] = False
    _save_catalog(site, raw)
    out = build.render_all(site)
    page = out[build.README]
    assert "On the way" not in page and "Gamma" not in page and "on the way" not in page
    assert "profile/assets/covers/gamma.svg" not in out


def test_on_the_way_switch_must_be_true_or_false(site):
    raw = _catalog_raw(site)
    raw["on_the_way"]["show"] = "no"
    _save_catalog(site, raw)
    with pytest.raises(CatalogError, match="`show` must be a bool"):
        load_catalog(site / build.CATALOG, set(art.MOTIFS))


def test_summary_line_is_available_as_a_placeholder(site):
    """Not on the page right now; `{{summary}}` in the template brings it back."""
    catalog = load_catalog(site / build.CATALOG, set(art.MOTIFS))
    line = readme.summary_block(readme.items(catalog, load_snapshot(site / build.SNAPSHOT)))
    assert line.startswith("**2 repositories open to members today, 1 on the way.**")
    assert "Latest release: [Beta App v0.9.0]" in line


def test_cards_name_only_the_tiers_switched_on(site):
    page = build.render_all(site)[build.README]
    assert "All members" not in page                      # standard: on_cards false
    assert "**Premium**" in page                          # premium: on_cards true, in the card and the legend
    assert build._tag("released", "standard", "All members", False) == (None, "none")
    assert build._tag("released", "premium", "Premium", True) == ("PREMIUM", "solid")


def test_stack_line_follows_the_cards_switch(site):
    assert "<sub>Python</sub>" not in build.render_all(site)[build.README]
    raw = _catalog_raw(site)
    raw["cards"]["stack"] = True
    _save_catalog(site, raw)
    assert "<sub>Python</sub>" in build.render_all(site)[build.README]


def test_pitch_longer_than_150_characters_fails(site):
    raw = _catalog_raw(site)
    raw["repos"]["alpha"]["pitch"] = "Word " * 31  # 154 characters once trimmed
    _save_catalog(site, raw)
    with pytest.raises(CatalogError, match="characters; keep it to 150"):
        load_catalog(site / build.CATALOG, set(art.MOTIFS))
