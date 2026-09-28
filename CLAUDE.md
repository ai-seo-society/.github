# ai-seo-society/.github: the organization profile

This repo renders the page at https://github.com/ai-seo-society: `profile/README.md`
and every image in `profile/assets/`. **This repo is PUBLIC, and so are its Actions
logs.** Anyone can read every file, every commit message and every workflow run.

## Commands (run from this folder)

```bash
uv run python -m profilegen update         # refresh + build + check: run after anything changes in the org
uv run python -m profilegen sync           # clone missing org repos into ../, fast-forward clean ones
uv run python -m profilegen refresh        # GitHub -> data/org.json (read-only gh calls)
uv run python -m profilegen build          # catalog + data -> README + SVGs (offline, deterministic)
uv run python -m profilegen check --live   # every gate, plus data/org.json vs GitHub
uv run python -m profilegen preview        # .preview/profile.html: the page as GitHub renders it
uv run pytest
```

Exit codes: 0 current and complete, 1 a gate failed, 2 gh/git/config trouble, 4 current
but a repo members can see has no catalog entry yet. `--ci` makes output safe for a
public log.

## Who changes what

- **Words** (human-approved): `templates/README.md.tmpl` for the page, one entry in
  `catalog.yaml` per repo.
- **Facts** (machine): `data/org.json`, written only by `refresh`: which reviewed repos
  members can see, their tier, whether they are empty, and their last releases.
- **Output**: `profile/` is written only by `build`. `check` fails on any byte `build`
  would not produce, and on any file under `profile/` it did not produce.
- **The autopilot** (`.github/workflows/autopilot.yml`) runs `update --ci` every hour
  and after each release, and commits fact changes on its own. It never changes words:
  it cannot add a repo to the page, because `refresh` only writes repos that already
  have a catalog entry. A new repo shows up as "waiting" (exit 4) until a person writes
  its entry.

## Architecture rules (enforced by tests/test_architecture.py)

- Only `profilegen/live.py` starts processes, calls gh or git, touches the network or
  reads outside this repo. `cli.py` wires it in. Every other module is pure and may
  import only what the test's allowlist names. A new module is pure by default.
- `build` is a pure function of `catalog.yaml`, `data/org.json`, `templates/` and
  `fonts/`. That is why CI can prove the page current with no network and no secrets.
- Words in images are glyph outlines (HarfBuzz + fontTools from `fonts/`), never SVG
  text: an SVG shown through `<img>` loads no fonts.
- Everything written uses LF line endings, so Windows and Linux builds are byte-identical.
- The header `<picture>` must never sit inside a link: GitHub's renderer then pulls the
  `<img>` out of it and the light/dark swap breaks. A test guards this.
- One HTML table per repo card: GitHub shades every second table row.

## Gates (in code, not in this file)

- `catalog.yaml`: unknown keys, non-https links, a `stack` that is not a list, a pitch
  that names a version or uses a banned hype word, a name or kicker that does not fit
  its cover. Each is a `CatalogError`.
- `data/org.json`: only semver tags, ISO dates and github.com release links survive
  `refresh`. Team names derive the tier and are dropped. No free text from GitHub.
- Privacy: every committable and rendered file is scanned with the maintainer's private
  deny-list and the secret rules. A finding names the file, line and rule, never the
  text. CI and the autopilot have no deny-list and say so; they cannot add words.
- Public logs: with `--ci`, nothing prints the name of a repo the catalog does not list.

## New artwork

Add a motif function in `profilegen/art.py` and register it in `MOTIFS` and
`MOTIF_DRAW`. Themes swap hues only (`THEMES`). Layout, spacing, sharp corners and the
semantic colours `SPARK` (the mark) and `ALERT` (something moved) stay fixed.

## Deliberately not here

- No members-only profile (`.github-private`) yet.
- No ledger: `data/org.json` is a snapshot you can always fetch again, and git history
  records what the page said, and when.
- No multi-tenancy: one org, one page.
