"""剧本解析结果的用户隔离文件存储。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.config import settings
from backend.rehearsal.models import ScriptAnalysis, ScriptSummary


_SCRIPT_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _scripts_dir(user_id: str) -> Path:
    path = settings.user_data_dir(user_id) / "rehearsal" / "scripts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _script_path(user_id: str, script_id: str) -> Path:
    if not _SCRIPT_ID_RE.fullmatch(script_id):
        raise ValueError("invalid script id")
    return _scripts_dir(user_id) / f"{script_id}.json"


def save_script(analysis: ScriptAnalysis, *, user_id: str) -> None:
    path = _script_path(user_id, analysis.script_id)
    path.write_text(
        json.dumps(analysis.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_script(script_id: str, *, user_id: str) -> ScriptAnalysis | None:
    path = _script_path(user_id, script_id)
    if not path.exists():
        return None
    return ScriptAnalysis.model_validate(json.loads(path.read_text(encoding="utf-8")))


def list_scripts(*, user_id: str) -> list[ScriptSummary]:
    result: list[ScriptSummary] = []
    for path in sorted(_scripts_dir(user_id).glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            analysis = ScriptAnalysis.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        result.append(ScriptSummary(
            script_id=analysis.script_id,
            title=analysis.title,
            version_label=analysis.version_label,
            scene_count=len(analysis.scenes),
            character_count=len(analysis.characters),
            prop_count=len(analysis.props),
            created_at=analysis.created_at,
        ))
    return result
