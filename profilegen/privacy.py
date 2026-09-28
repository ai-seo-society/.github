"""The privacy gate. This repository is public: nothing private may reach it.

Same rules as the release engine's leak gate: the deny-list (one case-insensitive
regex per line, `#` comments) plus the common secret shapes. A finding names the file,
the line and the rule, never the matched text, so the report is safe to print.

Pure: callers hand in the deny-list text and the file contents.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

SECRET_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}")),
    ("github token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}")),
    ("aws key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("stripe key", re.compile(r"\b[rs]k_live_[A-Za-z0-9]{20,}")),
]
PRIVATE_MARKER = re.compile(r"private:(start|end|line)")


class PrivacyViolation(Exception):
    """Something that must stay private is in a file this public repo would publish."""


@dataclass(frozen=True)
class Finding:
    rule: str
    where: str  # path, or path:line

    def __str__(self) -> str:
        return f"{self.rule} at {self.where}"


def deny_rules(denylist_text: str) -> list[tuple[str, re.Pattern[str]]]:
    rules = []
    for n, line in enumerate(denylist_text.splitlines(), 1):
        line = line.strip()
        if line and not line.startswith("#"):
            rules.append((f"deny-list #{n}", re.compile(line, re.I)))
    return rules


def scan(files: Mapping[str, bytes], deny: list[tuple[str, re.Pattern[str]]]) -> list[Finding]:
    findings: list[Finding] = []
    for rel, raw in sorted(files.items()):
        findings += [Finding(label, f"{rel} (path)") for label, rx in deny if rx.search(rel)]
        if b"\0" in raw[:8000]:
            continue  # binary (fonts): the path rules above are all that apply
        for n, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
            where = f"{rel}:{n}"
            if PRIVATE_MARKER.search(line):
                findings.append(Finding("private marker", where))
            findings += [Finding(label, where) for label, rx in deny + SECRET_RULES if rx.search(line)]
    return findings
