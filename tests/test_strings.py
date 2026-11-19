"""Every error a dialog can show has its text."""

from __future__ import annotations

import ast
import json
from pathlib import Path

COMPONENT = Path("custom_components/svs_subwoofer")


def _error_keys(node: ast.AST) -> set[str]:
    """Return the error keys set as errors[...] = "key" inside a node."""
    keys: set[str] = set()
    for item in ast.walk(node):
        if (
            isinstance(item, ast.Assign)
            and isinstance(item.targets[0], ast.Subscript)
            and isinstance(item.targets[0].value, ast.Name)
            and item.targets[0].value.id == "errors"
            and isinstance(item.value, ast.Constant)
        ):
            keys.add(item.value.value)
    return keys


def test_every_dialog_error_has_its_text() -> None:
    """Setup errors are in config.error, options errors in options.error.

    Steps shared by both flows (a mixin) need the text in both.
    """
    tree = ast.parse((COMPONENT / "config_flow.py").read_text(encoding="utf-8"))
    needed: dict[str, set[str]] = {"config": set(), "options": set()}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {getattr(base, "id", "") for base in node.bases}
        keys = _error_keys(node)
        if "ConfigFlow" in bases:
            needed["config"] |= keys
        elif "OptionsFlow" in bases:
            needed["options"] |= keys
        else:
            needed["config"] |= keys
            needed["options"] |= keys
    for name in ("strings.json", "translations/en.json"):
        strings = json.loads((COMPONENT / name).read_text(encoding="utf-8"))
        for section, keys in needed.items():
            missing = keys - set(strings[section].get("error", {}))
            assert not missing, f"{name} {section}.error lacks {sorted(missing)}"
