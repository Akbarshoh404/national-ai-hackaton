"""Import-direction rules of the modular monolith (scans every import, including lazy ones in functions).

    core           → nothing outside core
    data_pipeline  → core, intelligence.market
    intelligence   → never api or channels (nor the top-level entry points main / cli / seed*)
    api, channels  → anything below them
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
ENTRY_POINTS = ("app.main", "app.cli", "app.seed", "app.seed_v2")


def imports_of(package: str) -> list[tuple[str, int, str]]:
    """(file, line, imported module) for every absolute `app.*` import inside a package."""
    out = []
    for path in (APP / package.replace(".", "/")).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module and not node.level:
                mods = [node.module] if node.module != "app" else [f"app.{a.name}" for a in node.names]
            elif isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            for m in mods:
                if m == "app" or m.startswith("app."):
                    out.append((str(path.relative_to(APP)), node.lineno, m))
    return out


def _under(mod: str, *prefixes: str) -> bool:
    return any(mod == p or mod.startswith(p + ".") for p in prefixes)


@pytest.mark.parametrize("package,allowed,forbidden", [
    ("core", ("app.core",), None),
    ("data_pipeline", ("app.core", "app.data_pipeline", "app.intelligence.market"), None),
    ("intelligence", None, ("app.api", "app.channels", *ENTRY_POINTS)),
])
def test_import_direction(package, allowed, forbidden):
    bad = []
    for file, line, mod in imports_of(package):
        if allowed is not None and not _under(mod, *allowed):
            bad.append(f"{file}:{line} imports {mod}")
        if forbidden is not None and _under(mod, *forbidden):
            bad.append(f"{file}:{line} imports {mod}")
    assert not bad, "import-direction violations:\n" + "\n".join(bad)


def test_packages_exist_with_readme():
    for pkg in ("core", "data_pipeline", "intelligence", "intelligence/market", "intelligence/books",
                "intelligence/b2b", "intelligence/advisor", "api", "channels"):
        assert (APP / pkg / "__init__.py").exists(), pkg
    for pkg in ("core", "data_pipeline", "intelligence", "api", "channels"):
        assert (APP / pkg / "README.md").exists(), f"{pkg}/README.md missing"
