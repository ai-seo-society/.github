"""The boundary: only live.py (and the cli that wires it) may reach outside this repo.

Everything else must stay a pure function of the files in this repository. That is
what lets CI rebuild the page with no network and no clones, and prove it is current.
Pure modules get an ALLOWLIST of imports, not a blocklist: a new way to start a process
or open a socket is blocked by default instead of slipping through.
"""
import ast
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "profilegen"
BOUNDARY = {"live.py", "cli.py", "__main__.py"}
PURE_LOCAL = {"art", "text", "catalog", "readme", "build", "privacy", "preview"}
ALLOWED = {"__future__", "dataclasses", "functools", "pathlib", "re", "json", "hashlib", "math", "random",
           "html", "datetime", "typing", "base64", "yaml", "uharfbuzz", "fontTools"}
FORBIDDEN_NAMES = {"__import__", "eval", "exec", "compile", "open"}  # open: read through the paths you are handed
FORBIDDEN_ATTRS = {"expanduser", "home", "cwd", "system", "popen", "environ", "getenv"}


def _local(module: str, level: int) -> str | None:
    """The profilegen module an import names, or None if it is not ours."""
    if level:
        return module.split(".")[0] if module else ""
    if module == "profilegen":
        return ""
    return module.split(".")[1] if module.startswith("profilegen.") else None


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        where = f"{path.relative_to(PKG).as_posix()}:{getattr(node, 'lineno', '?')}"
        if isinstance(node, ast.Import):
            for a in node.names:
                local = _local(a.name, 0)
                if local is not None:
                    if local not in PURE_LOCAL:
                        found.append(f"{where} imports {a.name}")
                elif a.name.split(".")[0] not in ALLOWED:
                    found.append(f"{where} imports {a.name}")
        elif isinstance(node, ast.ImportFrom):
            local = _local(node.module or "", node.level)
            if local is None:
                if (node.module or "").split(".")[0] not in ALLOWED:
                    found.append(f"{where} imports {node.module}")
            else:
                targets = {local} if local else {a.name for a in node.names}
                if targets - PURE_LOCAL:
                    found.append(f"{where} imports profilegen.{', '.join(sorted(targets - PURE_LOCAL))}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_NAMES:
            found.append(f"{where} calls {node.func.id}()")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRS:
            found.append(f"{where} uses .{node.attr}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("~"):
            found.append(f"{where} names a path in a home folder")
    return found


def _pure_modules() -> list[Path]:
    return [p for p in sorted(PKG.rglob("*.py")) if p.relative_to(PKG).as_posix() not in BOUNDARY]


def test_pure_modules_never_reach_outside_the_repo():
    pure = _pure_modules()
    assert pure, "no modules found: did profilegen move?"
    problems = [v for p in pure for v in _violations(p)]
    assert not problems, "pure modules must not touch processes, the network, the home folder or live.py:\n" + "\n".join(problems)


def test_the_gate_catches_what_it_claims(tmp_path):
    fake_pkg = tmp_path / "profilegen"
    fake_pkg.mkdir()
    bad = fake_pkg / "bad.py"
    bad.write_text(
        "import subprocess\n"                       # 1 not allowed
        "from urllib import request\n"              # 2 not allowed
        "from . import live\n"                      # 3 boundary module
        "from .live import sync\n"                  # 4 boundary module
        "from profilegen import live as lv\n"       # 5 boundary module, absolute
        "import profilegen.cli\n"                   # 6 boundary module, dotted
        "import os\n"                               # 7 not allowed
        "from os import system\n"                   # 8 not allowed
        "import importlib\n"                        # 9 not allowed
        "__import__('socket')\n"                    # 10 dynamic import
        "from pathlib import Path\n"                # fine
        "Path('~/.claude').expanduser()\n"          # 11 home path + 12 expanduser
        "from . import catalog, text\n"             # fine
    )
    global PKG
    saved, PKG = PKG, fake_pkg
    try:
        found = _violations(bad)
    finally:
        PKG = saved
    assert len(found) == 12, found


def test_every_module_is_classified():
    """A new module is pure by default; putting it on the boundary is a decision."""
    names = {p.relative_to(PKG).as_posix() for p in PKG.rglob("*.py")}
    assert BOUNDARY <= names
    assert {p.stem for p in _pure_modules() if p.stem != "__init__"} <= PURE_LOCAL, \
        "a new pure module must be added to PURE_LOCAL"
