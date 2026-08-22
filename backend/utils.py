"""Shared utility functions."""
import json
import re
from pathlib import Path


def resolve_path_within(root: Path, *parts: str) -> Path:
    """Resolve a path and reject absolute/traversing components outside root."""
    root = root.resolve()
    candidate = root.joinpath(*parts).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("path escapes its allowed directory")
    return candidate


def safe_child_path(root: Path, filename: str) -> Path:
    """Resolve one plain filename below root; nested paths are not accepted."""
    if not filename or filename in {".", ".."} or Path(filename).name != filename:
        raise ValueError("filename must not contain a path")
    return resolve_path_within(root, filename)


def parse_json_response(content: str) -> dict | list:
    """Extract JSON from LLM response, handling markdown code blocks and raw prefixes."""
    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", content)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    for i, c in enumerate(content):
        if c in ("[", "{"):
            try:
                return json.loads(content[i:])
            except json.JSONDecodeError:
                pass
            break

    raise json.JSONDecodeError("No valid JSON found", content, 0)
