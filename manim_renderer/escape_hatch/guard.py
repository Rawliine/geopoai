"""Static guard linter for escape-hatch custom scene files."""

from __future__ import annotations

import ast
import re
import tokenize
from io import BytesIO
from pathlib import Path

_HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")

# Top-level module roots permitted in import statements.
_ALLOWED_MODULE_ROOTS = frozenset({
    "manim",
    "manim_renderer.theme",
    "manim_renderer.escape_hatch",
    "tools.tokens",
    "math",
    "numpy",
    "json",
})

_BANNED_MODULE_ROOTS = frozenset({
    "os",
    "sys",
    "subprocess",
    "requests",
    "pathlib",
    "socket",
    "urllib",
    "http",
    "shutil",
    "importlib",
})


class GuardViolation(Exception):
    """Raised when a custom scene file fails static checks."""


def _brand_font_names() -> frozenset[str]:
    try:
        from tools.tokens import load_tokens

        typo = load_tokens()["typography"]
        return frozenset(
            typo[k] for k in ("primary", "display", "mono", "math") if k in typo
        )
    except Exception:
        from manim_renderer.theme.typography import FONTS

        return frozenset(FONTS.values())


def _module_root(name: str) -> str:
    parts = name.split(".")
    if len(parts) >= 2 and parts[0] == "manim_renderer":
        if parts[1] == "theme":
            return "manim_renderer.theme"
        if parts[1] == "escape_hatch":
            return "manim_renderer.escape_hatch"
    if len(parts) >= 2 and parts[0] == "tools" and parts[1] == "tokens":
        return "tools.tokens"
    return parts[0]


def _is_allowed_import(module: str | None) -> bool:
    if not module:
        return False
    root = _module_root(module)
    if root in _BANNED_MODULE_ROOTS:
        return False
    if root in _ALLOWED_MODULE_ROOTS:
        return True
    if module == "manim" or module.startswith("manim."):
        return True
    if module.startswith("manim_renderer.theme."):
        return True
    if module.startswith("manim_renderer.escape_hatch."):
        return True
    return False


def _check_imports(tree: ast.AST, path: Path) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _is_allowed_import(alias.name):
                    raise GuardViolation(
                        f"{path}: disallowed import {alias.name!r}"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level and node.level > 0:
                raise GuardViolation(
                    f"{path}: relative imports are not allowed in escape scenes"
                )
            if not _is_allowed_import(module):
                raise GuardViolation(
                    f"{path}: disallowed import from {module!r}"
                )


def _source_without_comments(source: str) -> str:
    out: list[str] = []
    for tok in tokenize.tokenize(BytesIO(source.encode("utf-8")).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type in (tokenize.NL, tokenize.NEWLINE, tokenize.ENCODING):
            out.append(tok.line)
        elif tok.type == tokenize.STRING and tok.start[1] == 0:
            out.append(tok.line)
        else:
            out.append(tok.string)
    return "".join(out)


def _check_hex_literals(source: str, path: Path) -> None:
    scrubbed = _source_without_comments(source)
    for match in _HEX_RE.finditer(scrubbed):
        raise GuardViolation(
            f"{path}: hex color literal {match.group()!r} forbidden; "
            "use manim_renderer.theme.palette or tools.tokens"
        )


def _check_font_literals(tree: ast.AST, path: Path) -> None:
    banned = _brand_font_names()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in banned:
                raise GuardViolation(
                    f"{path}: font name literal {node.value!r} forbidden; "
                    "use manim_renderer.theme.typography.FONTS"
                )


def _base_names(node: ast.expr) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [node.attr]
    if isinstance(node, ast.Subscript):
        return _base_names(node.value)
    return []


def _check_subclass(tree: ast.AST, path: Path, class_name: str) -> None:
    found = False
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        found = True
        bases = [name for base in node.bases for name in _base_names(base)]
        if "EscapeHatchScene" not in bases:
            raise GuardViolation(
                f"{path}: class {class_name!r} must subclass EscapeHatchScene"
            )
    if not found:
        raise GuardViolation(
            f"{path}: class {class_name!r} not found in module"
        )


def lint_scene_file(path: Path, class_name: str) -> None:
    """Run all static checks. Raises ``GuardViolation`` on failure."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise GuardViolation(f"{path}: syntax error: {exc}") from exc

    _check_imports(tree, path)
    _check_hex_literals(source, path)
    _check_font_literals(tree, path)
    _check_subclass(tree, path, class_name)
