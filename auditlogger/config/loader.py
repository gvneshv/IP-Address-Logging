"""Load AuditLogger configuration with a small YAML fallback parser."""

from __future__ import annotations
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yaml")

# section -> required keys directly inside it.
# An empty tuple means the section itself must exist (even empty/disabled), but no specific key inside it is required.
_REQUIRED_SECTIONS: dict[str, tuple[str, ...]] = {
    "storage": ("log_file",),
    "telegram": (),
    "router": (),
}


class ConfigError(Exception):
    """Raised for problems with the AuditLogger config file - missing file, missing required sections, or malformed YAML.
    Deliberately a plain Exception subclass (not FileNotFoundError/ValueError/etc.)
    so callers can catch exactly this and only this to show a clean message instead of a traceback;
    anything else raised while loading config most likely indicates a real bug and should still surface normally.
    """


def _parse_scalar(value: str) -> Any:
    """Parse the scalar values supported by the fallback YAML loader."""
    value = value.strip()

    if value in {"true", "false"}:
        return value == "true"
    if value == "[]":
        return []
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value


def _indent_of(raw_line: str) -> int:
    """Return the number of leading spaces on a config line."""
    return len(raw_line) - len(raw_line.lstrip(" "))


def _load_simple_yaml(text: str) -> dict[str, Any]:
    """Load the indentation-nested section/key YAML shape used by the config.

    Supports arbitrary nesting depth (e.g. router -> connection -> address), which the config now requires.
    A "key:" line with nothing after the colon is treated as the start of a nested section only when the next non-blank line is indented further;
    otherwise it's an empty scalar (matches how a genuinely blank value like "address:" should behave).
    This is still a deliberately minimal parser - no lists of mappings, multi-line strings, or other full-YAML features are supported.
    Prefer installing PyYAML for anything beyond this project's own config shape.
    """
    lines: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if line.strip():
            lines.append((_indent_of(raw_line), line.strip()))

    root: dict[str, Any] = {}
    # Stack of (indent_level, dict_at_that_level); root sits below indent 0.
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for index, (indent, key_part) in enumerate(lines):
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if ":" not in key_part:
            continue

        key, _, value = key_part.partition(":")
        key = key.strip()
        value = value.strip()

        next_indent = lines[index + 1][0] if index + 1 < len(lines) else -1
        if not value and next_indent > indent:
            new_section: dict[str, Any] = {}
            parent[key] = new_section
            stack.append((indent, new_section))
        else:
            parent[key] = _parse_scalar(value)

    return root


def _validate_config(config: Any, path: Path) -> dict[str, Any]:
    """Raise ConfigError listing every missing/invalid required section at once.

    Checking eagerly here (once, right after loading) means a misconfigured file fails immediately and predictably at startup,
    rather than intermittently deep inside run_once() - e.g. the "telegram" section is only ever subscripted when a notifiable change actually occurs,
    so a missing key there could otherwise pass silently for weeks until the first real WAN change triggered a raw KeyError mid-run.
    """
    if not isinstance(config, dict):
        raise ConfigError(
            f"Config file at {path} must be a YAML mapping of sections (got {type(config).__name__})."
        )

    problems: list[str] = []
    for section, required_keys in _REQUIRED_SECTIONS.items():
        section_value = config.get(section)
        if not isinstance(section_value, dict):
            problems.append(f"missing or invalid '{section}' section")
            continue
        for key in required_keys:
            if key not in section_value:
                problems.append(f"missing '{section}.{key}'")

    if problems:
        example = path.with_name("config.example.yaml")
        raise ConfigError(
            f"Config file at {path} is incomplete: {'; '.join(problems)}. "
            f"Check {example.name} for the expected shape."
        )

    return config


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load configuration from config_path or the package config.yaml file.

    Raises ConfigError - never a bare FileNotFoundError, KeyError, or yaml.YAMLError - for every way this can fail:
    no file, a file that isn't valid YAML, or valid YAML that's missing a section main.py depends on.
    Callers (main.py) catch ConfigError specifically to print a short message instead of a traceback.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if not path.exists():
        example = path.with_name("config.example.yaml")
        raise ConfigError(
            f"Config file not found: {path}. Copy {example.name} to {path.name} and adjust values."
        )

    text = path.read_text(encoding="utf-8")

    try:
        import yaml
    except ModuleNotFoundError:
        config = _load_simple_yaml(text)
    else:
        try:
            config = yaml.safe_load(text) or {}
        except yaml.YAMLError as error:
            raise ConfigError(f"Config file at {path} is not valid YAML: {error}") from error

    return _validate_config(config, path)