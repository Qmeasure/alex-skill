from __future__ import annotations

import base64
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import requests

from .errors import PodcastEditorError


SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
RESOURCE_ID = "volc.bigasr.auc"
SUCCESS = "20000000"
PROCESSING = {"20000001", "20000002"}
MAX_LOCAL_AUDIO_BYTES = 100 * 1024 * 1024


def load_api_key(skill_root: str | Path | None = None) -> str:
    key = os.environ.get("VOLCENGINE_API_KEY", "").strip()
    if key:
        return key
    root = Path(skill_root) if skill_root else Path(__file__).resolve().parents[2]
    env_file = root / ".env"
    if env_file.is_file():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == "VOLCENGINE_API_KEY":
                value = value.strip().strip("\"'")
                if value:
                    return value
    raise PodcastEditorError(
        "missing_api_key",
        "没有找到 VOLCENGINE_API_KEY。请设置环境变量，或写入 Skill 目录的 .env。",
        status=500,
    )


def build_request(audio_path: str | Path, *, identify_speakers: bool) -> dict[str, Any]:
    path = Path(audio_path).expanduser().resolve()
    if not path.is_file():
        raise PodcastEditorError("input_not_found", f"找不到音频文件：{path}")
    size = path.stat().st_size
    if size > MAX_LOCAL_AUDIO_BYTES:
        raise PodcastEditorError(
            "audio_too_large",
            "本地音频超过 100 MiB，不能使用 base64 直传。",
            details={"sizeBytes": size, "limitBytes": MAX_LOCAL_AUDIO_BYTES},
            status=413,
        )
    audio_format = path.suffix.lstrip(".").lower() or "mp3"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "user": {"uid": "podcast_editor"},
        "audio": {"data": encoded, "format": audio_format},
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
            "enable_ddc": False,
            "show_utterances": True,
            "enable_speaker_info": identify_speakers,
            "enable_channel_split": False,
        },
    }


class VolcengineASR:
    def __init__(
        self,
        api_key: str,
        *,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        poll_interval: float = 5.0,
        max_polls: int = 120,
    ):
        if not api_key:
            raise ValueError("api_key must not be empty")
        self._api_key = api_key
        self._session = session or requests.Session()
        self._sleep = sleep
        self._poll_interval = poll_interval
        self._max_polls = max_polls

    def transcribe(self, audio_path: str | Path, *, identify_speakers: bool) -> dict[str, Any]:
        request_id = str(uuid.uuid4()).lower()
        common_headers = {
            "X-Api-Key": self._api_key,
            "X-Api-Resource-Id": RESOURCE_ID,
            "X-Api-Request-Id": request_id,
            "Content-Type": "application/json",
        }
        submit_headers = {**common_headers, "X-Api-Sequence": "-1"}
        submit = self._post_with_retry(
            SUBMIT_URL,
            headers=submit_headers,
            json_body=build_request(audio_path, identify_speakers=identify_speakers),
        )
        status = submit.headers.get("X-Api-Status-Code", "")
        if status != SUCCESS:
            raise self._api_failure("submit_failed", "转录任务提交失败。", submit)
        log_id = submit.headers.get("X-Tt-Logid", "")
        query_headers = dict(common_headers)
        if log_id:
            query_headers["X-Tt-Logid"] = log_id

        for _ in range(self._max_polls):
            self._sleep(self._poll_interval)
            query = self._post_with_retry(QUERY_URL, headers=query_headers, json_body={})
            status = query.headers.get("X-Api-Status-Code", "")
            if status == SUCCESS:
                try:
                    body = query.json()
                except requests.JSONDecodeError as exc:
                    raise PodcastEditorError("invalid_asr_response", "转录结果不是合法 JSON。", status=502) from exc
                if not isinstance(body, dict):
                    raise PodcastEditorError("invalid_asr_response", "转录结果格式无效。", status=502)
                return body
            if status in PROCESSING or not status:
                continue
            if status == "20000003":
                raise PodcastEditorError("silent_audio", "音频中没有可识别的语音。", status=422)
            raise self._api_failure("query_failed", "转录任务失败。", query)
        raise PodcastEditorError("asr_timeout", "等待转录结果超时。", status=504)

    def _post_with_retry(
        self, url: str, *, headers: dict[str, str], json_body: dict[str, Any]
    ) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self._session.post(url, headers=headers, json=json_body, timeout=(15, 60))
                if response.status_code < 500:
                    if response.status_code >= 400:
                        raise PodcastEditorError(
                            "asr_http_error",
                            f"火山引擎返回 HTTP {response.status_code}。",
                            status=502,
                        )
                    return response
            except PodcastEditorError:
                raise
            except requests.RequestException as exc:
                last_error = exc
            if attempt < 2:
                self._sleep(2**attempt)
        raise PodcastEditorError("asr_network_error", "连接火山引擎失败。", status=502) from last_error

    @staticmethod
    def _api_failure(code: str, message: str, response: requests.Response) -> PodcastEditorError:
        details = {
            "statusCode": response.headers.get("X-Api-Status-Code", ""),
            "message": response.headers.get("X-Api-Message", ""),
            "logId": response.headers.get("X-Tt-Logid", ""),
        }
        return PodcastEditorError(code, message, details=details, status=502)
