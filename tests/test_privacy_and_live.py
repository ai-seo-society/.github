"""The privacy gate never lets a deny-listed term through and never prints it; the
snapshot holds only reviewed repos and checked facts; public logs name nothing new;
sync leaves anything it does not own alone."""
import subprocess

import pytest

from profilegen import art, live, preview, privacy
from profilegen.text import Type, fit, measure


def test_denylist_hit_is_reported_without_the_value():
    rules = privacy.deny_rules("# clients\nacme\\s*corp\n\nsecret-client\\.example\n")
    findings = privacy.scan({"profile/README.md": b"hello\nwe did it for ACME Corp.\n",
                             "catalog.yaml": b"url: https://secret-client.example/x\n"}, rules)
    assert [str(f) for f in findings] == ["deny-list #4 at catalog.yaml:1", "deny-list #2 at profile/README.md:2"]
    assert all("acme" not in str(f).lower() for f in findings)


def test_secrets_and_private_markers_fail_even_without_a_denylist():
    token = "ghp_" + "a1B2" * 9
    marker = "private" + ":start"
    findings = privacy.scan({"x.md": f"token {token}\n{marker}\n".encode()}, [])
    assert {f.rule for f in findings} == {"github token", "private marker"}


def test_binary_files_only_get_path_rules():
    rules = privacy.deny_rules("acme")
    assert privacy.scan({"fonts/a.ttf": b"\0\0acme"}, rules) == []
    assert privacy.scan({"acme/a.ttf": b"\0\0"}, rules)[0].where == "acme/a.ttf (path)"


def test_tier_is_the_widest_audience_with_read_access():
    tiers = {"standard": ["team-s", "team-p"], "premium": ["team-p"]}
    assert live.tier_of({"team-s", "team-p"}, "private", tiers) == "standard"
    assert live.tier_of({"team-p"}, "private", tiers) == "premium"
    assert live.tier_of({"team-s"}, "private", tiers) is None  # standard team alone is not a defined tier
    assert live.tier_of(set(), "private", tiers) is None
    assert live.tier_of(set(), "public", tiers) == "public"


def test_the_autopilot_reads_tiers_from_its_secret(monkeypatch):
    monkeypatch.setenv("PROFILE_TIERS", '{"standard": ["s"]}')
    assert live.release_config() == {"tiers": {"standard": ["s"]}}
    monkeypatch.setenv("PROFILE_TIERS", "not json")
    with pytest.raises(live.GhError, match="PROFILE_TIERS"):
        live.release_config()


@pytest.fixture
def org(monkeypatch):
    """An invented org: a listed repo, a new one members can see, one nobody can see."""
    monkeypatch.setattr(live, "release_config", lambda: {"tiers": {"standard": ["hidden-team"]}})
    calls = {
        "orgs/o/repos?type=all&per_page=100&page=1": [
            {"name": "a", "visibility": "private"},
            {"name": "newbie", "visibility": "private"},
            {"name": "internal", "visibility": "private"},
            {"name": ".github", "visibility": "public"},
        ],
        "repos/o/a/teams?per_page=100&page=1": [{"slug": "hidden-team"}],
        "repos/o/newbie/teams?per_page=100&page=1": [{"slug": "hidden-team"}],
        "repos/o/internal/teams?per_page=100&page=1": [],
        "repos/o/a/commits?per_page=1": [{"sha": "1"}],
        "repos/o/a/releases?per_page=100": [
            {"tag_name": "v1.0.0", "published_at": "2026-01-01T00:00:00Z", "html_url": "https://github.com/o/a/releases/tag/v1.0.0"},
            {"tag_name": "v2-draft", "published_at": None, "html_url": "x", "draft": True},
            {"tag_name": "for ACME only", "published_at": "2026-02-01T00:00:00Z", "html_url": "https://github.com/o/a/releases/tag/x"},
            {"tag_name": "v1.1.0", "published_at": "2026-03-01T00:00:00Z", "html_url": "https://evil.example/x"},
        ],
    }
    monkeypatch.setattr(live, "gh_api", lambda path, allow_empty_repo=False: calls[path])


def test_snapshot_holds_only_listed_repos_and_checked_facts(org):
    snap, pending, notes = live.fetch_snapshot("o", listed={"a"})
    assert [r["name"] for r in snap["repos"]] == ["a"]
    assert snap["repos"][0] == {"name": "a", "tier": "standard", "empty": False, "url": "https://github.com/o/a",
                                "releases": [{"tag": "v1.0.0", "published": "2026-01-01T00:00:00Z",
                                              "url": "https://github.com/o/a/releases/tag/v1.0.0"}]}
    assert pending == ["newbie"]
    assert "hidden-team" not in repr(snap) and "ACME" not in repr(snap)
    assert notes.count("a: a release with an unexpected tag, date or link was left out") == 2
    assert "internal: no member tier can read it, left out" in notes


def test_public_logs_never_name_an_unlisted_repo(org):
    _, pending, notes = live.fetch_snapshot("o", listed={"a"}, redact=True)
    assert pending == ["newbie"]  # returned to the caller, which prints only a count in --ci
    assert not any("internal" in n or "newbie" in n for n in notes)


def test_origin_must_be_exactly_this_repo():
    assert live._same_repo("https://github.com/ai-seo-society/agentic-seo-system.git", "ai-seo-society", "agentic-seo-system")
    assert live._same_repo("git@github.com:ai-seo-society/agentic-seo-system", "ai-seo-society", "agentic-seo-system")
    assert not live._same_repo("https://github.com/ai-seo-society/agentic-seo-system-app.git", "ai-seo-society", "agentic-seo-system")
    assert not live._same_repo("https://github.com/someone/agentic-seo-system.git", "ai-seo-society", "agentic-seo-system")


def test_sync_leaves_folders_it_does_not_own_alone(tmp_path, monkeypatch):
    def git(*args, cwd):
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

    (tmp_path / "no-origin").mkdir()
    git("init", "-q", cwd=tmp_path / "no-origin")
    (tmp_path / "agentic-seo-system").mkdir()
    git("init", "-q", cwd=tmp_path / "agentic-seo-system")
    git("remote", "add", "origin", "https://github.com/o/agentic-seo-system-app.git", cwd=tmp_path / "agentic-seo-system")
    (tmp_path / "plain").mkdir()
    monkeypatch.setattr(live, "gh_api_all", lambda path: [
        {"name": n, "default_branch": "main"} for n in ("no-origin", "agentic-seo-system", "plain")])
    report = live.sync("o", tmp_path, dry_run=True)
    assert report == [
        "skip   agentic-seo-system: its origin is not github.com/o/agentic-seo-system",
        "skip   no-origin: its origin is not github.com/o/no-origin",
        "skip   plain: folder exists but is not a git clone",
    ]


def test_preview_inlines_every_image_and_swaps_the_header():
    rendered = ('<themed-picture><picture><source srcset="./assets/header-dark.svg"><img src="./assets/header-dark.svg">'
                '</picture></themed-picture><a href="./assets/covers/a.svg"><img src="./assets/covers/a.svg"></a>')
    assets = {"assets/header-dark.svg": "<svg>d</svg>", "assets/header-light.svg": "<svg>l</svg>",
              "assets/covers/a.svg": "<svg>a</svg>"}
    out = preview.page("<b>{{org_name}}</b>{{body}}{{css_light}}{{css_dark}}{{avatar}}{{org}}{{state}}", rendered,
                       assets, ".markdown-body{}", ".markdown-body{}", b"\x89PNG....", "o", "Org", "alt", "s")
    assert "./assets/" not in out and "hdr-light" in out and "data:image/png" in out
    assert '[data-gh="light"] .markdown-body' in out and '[data-gh="dark"] .markdown-body' in out
    with pytest.raises(preview.PreviewError):
        preview.page("{{body}}", '<img src="./assets/covers/missing.svg">', assets, "", "", b"", "o", "O", "a", "s")


def test_text_fits_its_box():
    t, lines = fit("AGENTIC SEO SYSTEM APP", Type("display", 800, 96), 500, 3, 56)
    assert len(lines) <= 3 and all(measure(line, t) <= 500 for line in lines)


def test_every_motif_draws():
    for motif in art.MOTIFS:
        out = art.cover("x", "Name", "Kicker", motif, "ALL MEMBERS", "outline")
        assert out.startswith("<svg") and out.endswith("</svg>\n")
