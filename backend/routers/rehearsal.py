"""奇点剧团排练领域 API。"""

from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pypdf import PdfReader

from backend.auth import get_current_user
from backend.rehearsal.agent import ScriptAnalysisAgent
from backend.rehearsal.models import ScriptAnalysis, ScriptParseRequest
from backend.rehearsal.storage import get_script, list_scripts, save_script


router = APIRouter(prefix="/api/rehearsal", tags=["rehearsal"])
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}


def _analyze(*, title: str, version_label: str, script_text: str, user_id: str, source_filename: str | None = None):
    analysis = ScriptAnalysisAgent().run(
        title=title,
        version_label=version_label,
        script_text=script_text,
        script_id=uuid4().hex,
    )
    if source_filename:
        analysis.warnings.insert(0, f"来源文件：{source_filename}")
    save_script(analysis, user_id=user_id)
    return analysis


@router.post("/scripts/parse", response_model=ScriptAnalysis)
async def parse_script(
    request: ScriptParseRequest,
    user_id: str = Depends(get_current_user),
):
    """解析已经读取到内存中的剧本文本，便于前端和测试稳定调用。"""
    return _analyze(
        title=request.title,
        version_label=request.version_label,
        script_text=request.script_text,
        user_id=user_id,
    )


@router.post("/scripts/parse-file", response_model=ScriptAnalysis)
async def parse_script_file(
    file: UploadFile = File(...),
    version_label: str = "v1",
    user_id: str = Depends(get_current_user),
):
    """解析 Markdown、纯文本或可提取文本的 PDF 剧本。"""
    filename = file.filename or "untitled-script.txt"
    suffix = Path(filename).suffix.lower()
    if suffix not in _TEXT_EXTENSIONS and suffix != ".pdf":
        raise HTTPException(400, "当前仅支持 .txt、.md、.markdown 和 .pdf 剧本")

    raw = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, "单个剧本不能超过 20 MB")

    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(raw))
        script_text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    else:
        try:
            script_text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            script_text = raw.decode("gb18030")

    if not script_text.strip():
        raise HTTPException(400, "剧本内容为空，无法解析")

    return _analyze(
        title=Path(filename).stem,
        version_label=version_label,
        script_text=script_text,
        user_id=user_id,
        source_filename=filename,
    )


@router.get("/scripts")
def get_scripts(user_id: str = Depends(get_current_user)):
    return {"items": list_scripts(user_id=user_id)}


@router.get("/scripts/{script_id}", response_model=ScriptAnalysis)
def get_script_detail(script_id: str, user_id: str = Depends(get_current_user)):
    try:
        analysis = get_script(script_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的剧本 ID")
    if analysis is None:
        raise HTTPException(404, "剧本解析结果不存在")
    return analysis
