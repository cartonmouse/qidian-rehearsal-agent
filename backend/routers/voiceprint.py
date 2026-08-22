"""Voiceprint management routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from backend.auth import get_current_user
from backend.models import VoiceprintCredentials

router = APIRouter(prefix="/api")


@router.get("/voiceprint/status")
def voiceprint_status(user_id: str = Depends(get_current_user)):
    """返回用户声纹配置状态（未配置/已配置未注册/已注册）。"""
    from backend.copilot import voiceprint_store

    return voiceprint_store.status_summary(user_id)


@router.put("/voiceprint/credentials")
async def voiceprint_put_credentials(
    payload: VoiceprintCredentials,
    user_id: str = Depends(get_current_user),
):
    """保存腾讯云凭据。保存前先 ping 一下验证有效性。"""
    from backend.copilot import voiceprint_store
    from backend.copilot.voiceprint import VoiceprintClient

    client = VoiceprintClient(
        secret_id=payload.secret_id,
        secret_key=payload.secret_key,
        app_id=payload.app_id,
    )
    if not await client.ping():
        raise HTTPException(400, "腾讯云凭据无效或网络不通，请检查 SecretId / SecretKey")

    data = voiceprint_store.load(user_id)
    data["credentials"] = payload.model_dump()
    voiceprint_store.save(user_id, data)
    return {"ok": True}


@router.post("/voiceprint/enroll")
async def voiceprint_enroll(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """上传 WAV 文件注册候选人声纹。前端应录制 ≥6 秒 16kHz mono WAV。"""
    from backend.copilot import voiceprint_store
    from backend.copilot.voiceprint import extract_pcm_from_wav

    client = voiceprint_store.get_client(user_id)
    if client is None:
        raise HTTPException(400, "请先在设置页配置腾讯云凭据")

    wav_bytes = await file.read()
    if not wav_bytes:
        raise HTTPException(400, "上传文件为空")
    try:
        pcm_bytes = extract_pcm_from_wav(wav_bytes)
    except ValueError as exc:
        raise HTTPException(400, f"WAV 解析失败：{exc}")

    if len(pcm_bytes) < 64000:
        raise HTTPException(400, "录音太短，至少 2 秒")

    speaker_nick = f"techspar_{user_id}"
    voice_print_id = await client.enroll(speaker_nick, pcm_bytes)
    if not voice_print_id:
        raise HTTPException(500, "腾讯云声纹注册失败，请检查日志")

    data = voiceprint_store.load(user_id)
    data["enrollment"] = {
        "voice_print_id": voice_print_id,
        "speaker_nick": speaker_nick,
        "enrolled_at": datetime.now().isoformat(),
    }
    voiceprint_store.save(user_id, data)
    return {"ok": True, "enrolled_at": data["enrollment"]["enrolled_at"]}


@router.delete("/voiceprint/enroll")
async def voiceprint_unenroll(user_id: str = Depends(get_current_user)):
    """删除已注册声纹（本地 + 腾讯云端）。保留凭据。"""
    from backend.copilot import voiceprint_store

    voice_print_id = voiceprint_store.get_voice_print_id(user_id)
    if voice_print_id:
        client = voiceprint_store.get_client(user_id)
        if client is not None:
            await client.delete(voice_print_id)

    data = voiceprint_store.load(user_id)
    data.pop("enrollment", None)
    voiceprint_store.save(user_id, data)
    return {"ok": True}
