# ai-seo-society/.github

The source of the profile page at [github.com/ai-seo-society](https://github.com/ai-seo-society).

`profile/README.md` and the artwork in `profile/assets/` are generated from
`catalog.yaml` (the words), `templates/README.md.tmpl` (the page) and `data/org.json`
(what GitHub says: repositories, tiers, releases).

```bash
uv run python -m profilegen update   # read the org, rebuild the page, run every check
uv run pytest
```

Fonts in `fonts/` are Outfit and JetBrains Mono under the SIL Open Font License
(`fonts/OFL-*.txt`).
