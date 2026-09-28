"""One self-contained HTML page that shows profile/README.md as GitHub renders it, in
GitHub light and dark, at desktop and phone width. For approving a change before it
goes public. Pure: the caller hands in GitHub's rendering, the stylesheets and images.
"""
from __future__ import annotations

import base64
import re

PLACEHOLDERS = ("css_light", "css_dark", "avatar", "org_name", "org", "state", "body")


class PreviewError(Exception):
    """The rendered README references an image the build did not produce."""


def _uri(mime: str, data: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def page(template: str, rendered: str, assets: dict[str, str], css_light: str, css_dark: str,
         avatar: bytes, org: str, org_name: str, header_alt: str, state: str) -> str:
    """assets: {path under profile/: svg text}. state: one line under the org name."""
    svg = {rel: _uri("image/svg+xml", text.encode("utf-8")) for rel, text in assets.items()}
    # GitHub picks the header by the visitor's OS theme; in the preview the buttons do.
    body = re.sub(
        r"<themed-picture.*?</themed-picture>",
        lambda m: (f'<img class="hdr hdr-dark" src="{svg["assets/header-dark.svg"]}" width="100%" alt="{header_alt}">'
                   f'<img class="hdr hdr-light" src="{svg["assets/header-light.svg"]}" width="100%" alt="">'),
        rendered, flags=re.S)
    body = re.sub(r'(src|href)="\./(assets/[^"]+\.svg)"',
                  lambda m: f'{m.group(1)}="{svg[m.group(2)]}"' if m.group(2) in svg else m.group(0), body)
    if "./assets/" in body:
        raise PreviewError("the rendered README points at an image the build did not produce")

    unknown = set(re.findall(r"\{\{(\w+)\}\}", template)) - set(PLACEHOLDERS)
    if unknown:
        raise PreviewError(f"templates/preview.html has unknown placeholders: {', '.join(sorted(unknown))}")
    mime = "image/png" if avatar[:4] == b"\x89PNG" else "image/jpeg"
    values = {"css_light": _scope(css_light, "light"), "css_dark": _scope(css_dark, "dark"),
              "avatar": _uri(mime, avatar), "org_name": org_name, "org": org, "state": state, "body": body}
    # One pass: inserted CSS and HTML are never scanned for placeholders themselves.
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], template)


def _scope(css: str, mode: str) -> str:
    """GitHub's stylesheet targets .markdown-body; scope it to one theme of the frame."""
    return css.replace(".markdown-body", f'[data-gh="{mode}"] .markdown-body')
