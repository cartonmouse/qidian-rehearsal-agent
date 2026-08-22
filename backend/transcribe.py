"""语音转写模块：两条独立链路。

短音频（几秒~几分钟，≤10MB）：
    base64 data URI → DashScope qwen3-asr-flash 同步 chat/completions，零 OSS。

长音频（录音复盘，可能几十分钟）：
    bytes → 阿里云 OSS（signed URL, 1h 过期）→ DashScope qwen3-asr-flash-filetrans 异步 + 轮询。
"""
import base64
import uuid
import time
import logging
import requests

import oss2

from backend.llm_provider import resolve_dashscope_key, resolve_oss_config

logger = logging.getLogger("uvicorn")

_DASHSCOPE_SYNC = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
_DASHSCOPE_SUBMIT = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
_DASHSCOPE_QUERY = "https://dashscope.aliyuncs.com/api/v1/tasks/"

# DashScope 同步端点限制：单次输入 ≤10MB、时长 ≤5min。
# base64 会让体积 ×4/3，因此原始音频留 7MB 安全线。
_SYNC_MAX_RAW_BYTES = 7 * 1024 * 1024

_AUDIO_MIME = {
    ".webm": "audio/webm",
    ".mp3": "audio/mp3",
    ".wav": "audio/wav",
    ".m4a": "audio/m4a",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}


def transcribe_short(audio_bytes: bytes, suffix: str = ".webm") -> str:
    """短音频同步转写：base64 data URI → DashScope qwen3-asr-flash。

    适用于答题语音输入等 ≤5min / ≤7MB 的短片段，不依赖对象存储。
    超过限制请走 transcribe_long（长音频 filetrans 链路）。
    """
    api_key = resolve_dashscope_key()
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY not configured")

    if not audio_bytes:
        raise RuntimeError("empty audio payload")

    if len(audio_bytes) > _SYNC_MAX_RAW_BYTES:
        raise RuntimeError(
            f"audio too large for sync endpoint: {len(audio_bytes)} bytes "
            f"(limit {_SYNC_MAX_RAW_BYTES}); use transcribe_long instead"
        )

    mime = _AUDIO_MIME.get(suffix.lower(), "audio/webm")
    data_uri = f"data:{mime};base64,{base64.b64encode(audio_bytes).decode()}"

    payload = {
        "model": "qwen3-asr-flash",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "input_audio", "input_audio": {"data": data_uri}},
                ],
            }
        ],
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(_DASHSCOPE_SYNC, headers=headers, json=payload, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"DashScope sync ASR failed [{resp.status_code}]: {resp.text}")

    data = resp.json()
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"DashScope response missing transcript: {e}; body={data}")

    logger.info(f"Sync transcription done: {len(text)} chars")
    return text


def _upload_to_oss(audio_bytes: bytes, suffix: str) -> str:
    """Upload bytes to Alibaba Cloud OSS, return a signed URL (1h expiry).

    Bucket can stay private — DashScope filetrans pulls via the signature.
    """
    cfg = resolve_oss_config()
    missing = [
        name for name, val in (
            ("ALIYUN_OSS_ACCESS_KEY_ID", cfg["access_key_id"]),
            ("ALIYUN_OSS_ACCESS_KEY_SECRET", cfg["access_key_secret"]),
            ("ALIYUN_OSS_BUCKET", cfg["bucket"]),
            ("ALIYUN_OSS_ENDPOINT", cfg["endpoint"]),
        ) if not val
    ]
    if missing:
        raise RuntimeError(f"Alibaba OSS not configured: missing {', '.join(missing)}")

    auth = oss2.Auth(cfg["access_key_id"], cfg["access_key_secret"])
    bucket = oss2.Bucket(auth, cfg["endpoint"], cfg["bucket"])
    key = f"audio/{uuid.uuid4().hex}{suffix}"

    bucket.put_object(key, audio_bytes)
    # slash_safe=True 保留 key 里的 "/"，避免 DashScope 取不到文件
    url = bucket.sign_url("GET", key, 3600, slash_safe=True)
    logger.info(f"Uploaded to OSS: {key}")
    return url


def transcribe_long(audio_bytes: bytes, suffix: str = ".webm") -> str:
    """长音频异步转写：阿里云 OSS → DashScope qwen3-asr-flash-filetrans 轮询。

    给录音复盘场景用，可支持几十分钟~几小时的面试录音。
    短音频请优先用 transcribe_short（更快、零 OSS 依赖）。
    """
    api_key = resolve_dashscope_key()
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY not configured")

    file_url = _upload_to_oss(audio_bytes, suffix)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    payload = {
        "model": "qwen3-asr-flash-filetrans",
        "input": {"file_url": file_url},
        "parameters": {"channel_id": [0]},
    }

    resp = requests.post(_DASHSCOPE_SUBMIT, headers=headers, json=payload, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"Transcription submit failed: {resp.text}")

    task_id = resp.json()["output"]["task_id"]
    logger.info(f"Transcription task: {task_id}")

    query_headers = {"Authorization": f"Bearer {api_key}"}
    for _ in range(300):
        time.sleep(3)
        qr = requests.get(_DASHSCOPE_QUERY + task_id, headers=query_headers, timeout=30)
        output = qr.json().get("output", {})
        status = output.get("task_status", "").upper()

        if status == "SUCCEEDED":
            text = _extract_text(output)
            logger.info(f"Transcription done: {len(text)} chars")
            return text
        elif status in ("FAILED", "UNKNOWN"):
            raise RuntimeError(f"Transcription {status}: {output.get('message', '')}")

    raise RuntimeError("Transcription timed out")


def _extract_text(output: dict) -> str:
    """Fetch transcription result and extract text."""
    # file_url 模式: result.transcription_url（单数）
    result = output.get("result", {})
    url = result.get("transcription_url")
    if not url:
        # file_urls 模式 fallback: results[].transcription_url
        for item in output.get("results", []):
            url = item.get("transcription_url")
            if url:
                break
    if not url:
        return ""

    resp = requests.get(url, timeout=60)
    if resp.status_code != 200:
        return ""

    data = resp.json()
    texts = []
    for transcript in data.get("transcripts", []):
        text = transcript.get("text", "")
        if text:
            texts.append(text)
    return "\n".join(texts)
