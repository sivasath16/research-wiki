"""
Extract dependency names from package manifests.
Supports: requirements.txt, package.json, go.mod, Cargo.toml, pom.xml, build.gradle
Used to populate repo.dependencies for cross-repo detection in chat.
"""
import json
import re
from pathlib import Path
from typing import List


def extract_dependencies(file_tree: List[str], repo_root: str) -> List[str]:
    """
    Walk known manifest files in the repo and return a deduplicated list
    of dependency names (lowercase, normalized).
    """
    deps: set[str] = set()
    root = Path(repo_root)

    manifest_parsers = {
        "requirements.txt": _parse_requirements,
        "requirements/base.txt": _parse_requirements,
        "requirements/prod.txt": _parse_requirements,
        "package.json": _parse_package_json,
        "go.mod": _parse_go_mod,
        "Cargo.toml": _parse_cargo_toml,
        "pom.xml": _parse_pom_xml,
        "build.gradle": _parse_gradle,
        "build.gradle.kts": _parse_gradle,
        "pyproject.toml": _parse_pyproject_toml,
    }

    for rel_path, parser in manifest_parsers.items():
        full_path = root / rel_path
        if full_path.exists():
            try:
                text = full_path.read_text(encoding="utf-8", errors="ignore")
                deps.update(parser(text))
            except Exception:
                continue

    return sorted(deps)


def _normalize(name: str) -> str:
    """Lowercase and strip version specifiers."""
    return re.split(r"[>=<!~\^@\s]", name.strip())[0].strip().lower().replace("_", "-")


def _parse_requirements(text: str) -> List[str]:
    deps = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        name = _normalize(line)
        if name:
            deps.append(name)
    return deps


def _parse_package_json(text: str) -> List[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    deps = []
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        for name in data.get(section, {}).keys():
            # Strip scope prefix for matching: @org/repo → repo
            clean = name.lstrip("@").split("/")[-1]
            deps.append(_normalize(clean))
    return deps


def _parse_go_mod(text: str) -> List[str]:
    deps = []
    in_require = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("require ("):
            in_require = True
            continue
        if in_require and line == ")":
            in_require = False
            continue
        if in_require or line.startswith("require "):
            parts = line.replace("require ", "").split()
            if parts:
                # github.com/owner/repo → repo
                module = parts[0].split("/")[-1]
                deps.append(_normalize(module))
    return deps


def _parse_cargo_toml(text: str) -> List[str]:
    deps = []
    in_deps = False
    for line in text.splitlines():
        line = line.strip()
        if line in ("[dependencies]", "[dev-dependencies]", "[build-dependencies]"):
            in_deps = True
            continue
        if line.startswith("[") and in_deps:
            in_deps = False
            continue
        if in_deps and "=" in line:
            name = line.split("=")[0].strip()
            deps.append(_normalize(name))
    return deps


def _parse_pom_xml(text: str) -> List[str]:
    # Simple regex — avoid lxml dependency
    return [_normalize(m) for m in re.findall(r"<artifactId>([^<]+)</artifactId>", text)]


def _parse_gradle(text: str) -> List[str]:
    deps = []
    for m in re.finditer(r"""['"]([\w.\-]+):([\w.\-]+):([\w.\-]+)['"]""", text):
        deps.append(_normalize(m.group(2)))
    return deps


def _parse_pyproject_toml(text: str) -> List[str]:
    deps = []
    in_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in ('[tool.poetry.dependencies]', '[project]'):
            in_deps = True
            continue
        if stripped.startswith("[") and in_deps:
            in_deps = False
        if in_deps:
            # Handle both `package = "^1.0"` and `"package>=1.0"` styles
            if "=" in stripped:
                name = stripped.split("=")[0].strip().strip('"')
                if name and not name.startswith("#"):
                    deps.append(_normalize(name))
    # Also handle PEP 517 dependencies list
    for m in re.finditer(r'"([\w\-]+)[\s><=!]', text):
        deps.append(_normalize(m.group(1)))
    return list(set(deps))
