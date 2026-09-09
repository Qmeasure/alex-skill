#!/usr/bin/env python3
"""音频/视频转文字。

火山引擎豆包录音文件识别模型 2.0（标准版）—— 句级时间戳 + 说话人分离。

用法:
  transcribe.py <音频文件> [输出.txt] [--plain]

只依赖 python3 标准库 + ffmpeg/ffprobe + oss2（上传中转用）。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

# 豆包录音文件识别模型 2.0（标准版，异步 提交/查询）。
# 该接口 audio 只接受 url，不支持 base64 直传，所以本地文件需先中转到公网可访问的 OSS。
VOLC_SUBMIT_ENDPOINT = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
VOLC_QUERY_ENDPOINT = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
VOLC_RESOURCE_ID = "volc.seedasr.auc"
VOLC_OK = "20000000"
VOLC_PROCESSING = {"20000001", "20000002"}  # 处理中 / 排队中
VOLC_POLL_INTERVAL = float(os.environ.get("VOLC_POLL_INTERVAL", "3"))
VOLC_POLL_TIMEOUT = float(os.environ.get("VOLC_POLL_TIMEOUT", "1800"))  # 30 分钟

# 本地文件 -> 公网 URL 的中转桶（阿里云 OSS，深圳）。
OSS_ENDPOINT = os.environ.get("AUDIO_TRANSCRIBE_OSS_ENDPOINT", "oss-cn-shenzhen.aliyuncs.com")
OSS_BUCKET = os.environ.get("AUDIO_TRANSCRIBE_OSS_BUCKET", "audio-transcipt")
OSS_URL_TTL = 4 * 3600  # 签名 URL 有效期，覆盖文档里"最长 3 小时"的任务时延

# 标准版单文件时长上限 5 小时；不再需要为绕过体积限制而切块。
MAX_DURATION_SECONDS = 5 * 3600


class TranscribeError(Exception):
    pass


# ──────────────────────────── 凭证 ────────────────────────────

def load_dotenv() -> None:
    """把 skill 根目录下 .env 的 KEY=VALUE 灌进 os.environ（不覆盖已有环境变量）。"""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def api_key(env_name: str) -> str:
    """env 变量优先，其次 skill 目录下的 .env。"""
    load_dotenv()
    key = os.environ.get(env_name, "").strip()
    if not key:
        raise TranscribeError(
            f"缺少 {env_name}。要么 export {env_name}=...，要么写进 skill 目录下的 .env"
        )
    return key


# ──────────────────────────── 音频预处理 ────────────────────────────

def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise TranscribeError(f"缺少 {tool}，请先 `brew install ffmpeg`")


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def normalize(src: Path, workdir: Path) -> Path:
    """转成 16k 单声道 mp3，兼容 m4a/flac/ogg/mp4/mkv 等任意输入格式。"""
    duration = probe_duration(src)
    if duration > MAX_DURATION_SECONDS:
        raise TranscribeError(
            f"音频时长 {duration/3600:.1f}h 超过标准版 5h 上限，请先自行切分"
        )

    out = workdir / "audio.mp3"
    cmd = ["ffmpeg", "-v", "error", "-i", str(src), "-vn", "-ar", "16000", "-ac", "1",
           "-b:a", "64k", str(out)]
    run = subprocess.run(cmd, capture_output=True, text=True)
    if run.returncode != 0:
        raise TranscribeError(f"ffmpeg 转码失败: {run.stderr[-400:]}")
    if not out.is_file() or out.stat().st_size < 1024:
        raise TranscribeError("转码后没有得到有效音频，检查源文件是否含音轨")
    return out


# ──────────────────────────── OSS 中转上传 ────────────────────────────

def upload_to_oss(path: Path) -> tuple[str, "object", str]:
    """上传本地文件到 OSS，返回 (签名 URL, bucket 对象, object key)。

    豆包录音文件识别模型 2.0 的 audio 字段只接受 url，不支持 base64 直传，
    所以本地文件必须先中转到一个公网可访问的地址。
    """
    try:
        import oss2
    except ImportError as e:
        raise TranscribeError("缺少 oss2，请先 `pip3 install oss2`") from e

    ak = api_key("ALIBABA_CLOUD_ACCESS_KEY_ID")
    sk = api_key("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
    # .env 在 api_key() 里才会被加载进 os.environ，所以这两个必须现读，不能用模块级常量
    endpoint = os.environ.get("AUDIO_TRANSCRIBE_OSS_ENDPOINT", OSS_ENDPOINT)
    oss_bucket_name = os.environ.get("AUDIO_TRANSCRIBE_OSS_BUCKET", OSS_BUCKET)
    auth = oss2.Auth(ak, sk)
    bucket = oss2.Bucket(auth, endpoint, oss_bucket_name)

    key = f"audio-transcribe/{int(time.time())}-{uuid.uuid4().hex[:8]}-{path.name}"
    bucket.put_object_from_file(key, str(path))
    url = bucket.sign_url("GET", key, OSS_URL_TTL)
    return url, bucket, key


def cleanup_oss(bucket, key: str) -> None:
    try:
        bucket.delete_object(key)
    except Exception as e:  # noqa: BLE001 - 清理失败不应影响主流程
        print(f"警告: 清理 OSS 临时文件失败: {e}", file=sys.stderr)


# ──────────────────────────── 火山引擎豆包 ────────────────────────────

def volc_request(url: str, key: str, task_id: str, extra_headers: dict, body: dict) -> tuple[str, str, dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "X-Api-Key": key,
            "X-Api-Resource-Id": VOLC_RESOURCE_ID,
            "X-Api-Request-Id": task_id,
            "Content-Type": "application/json",
            **extra_headers,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            status = resp.headers.get("x-api-status-code", "")
            message = resp.headers.get("x-api-message", "")
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        raise TranscribeError(
            f"火山引擎 HTTP {e.code}: {e.headers.get('x-api-message') or e.read()[:200]}"
        ) from e
    except urllib.error.URLError as e:
        raise TranscribeError(f"连接火山引擎失败: {e.reason}") from e
    return status, message, (json.loads(raw) if raw.strip() else {})


def build_asr_request() -> dict:
    """构造提交任务的 request 对象。

    热词表 ID 必须在这里现读，不能提到模块级常量：.env 是懒加载的
    （只有 api_key() 里的 load_dotenv() 才灌进 os.environ），模块级常量在
    import 时就求值，那时 .env 还没读进来。写成常量的后果是热词静默失效
    ——不报错、不告警，就是不生效。
    """
    load_dotenv()
    req = {
        "model_name": "bigmodel",
        "enable_itn": True,       # 口语数字/金额/日期转阿拉伯数字："一九七零年" → "1970 年"
        "enable_punc": True,      # 补逗号、句号、问号
        "enable_ddc": True,       # 语义顺滑：删停顿词、语气词、语义重复词
        "enable_speaker_info": True,
        "show_utterances": True,  # enable_speaker_info 依赖它才返回说话人
    }
    table_id = os.environ.get("VOLC_BOOSTING_TABLE_ID", "").strip()
    if table_id:
        # 热词表走控制台自学习平台配置，corpus 与 enable_auto_lang 互斥（本脚本不设后者）
        req["corpus"] = {"boosting_table_id": table_id}
    return req


def volcengine_transcribe(path: Path, key: str) -> list[dict]:
    """豆包录音文件识别模型 2.0：先中转到 OSS 拿公网 URL，再提交任务、轮询结果。"""
    url, bucket, oss_key = upload_to_oss(path)
    try:
        request_id = str(uuid.uuid4())
        status, message, _ = volc_request(
            VOLC_SUBMIT_ENDPOINT, key, request_id,
            {"X-Api-Sequence": "-1"},
            {
                "audio": {"url": url, "format": "mp3"},
                "request": build_asr_request(),
            },
        )
        if status != VOLC_OK:
            raise TranscribeError(f"火山引擎提交任务失败 {status}: {message}")

        deadline = time.monotonic() + VOLC_POLL_TIMEOUT
        while True:
            status, message, body = volc_request(VOLC_QUERY_ENDPOINT, key, request_id, {}, {})
            if status == VOLC_OK:
                break
            if status not in VOLC_PROCESSING:
                raise TranscribeError(f"火山引擎识别失败 {status}: {message}")
            if time.monotonic() > deadline:
                raise TranscribeError(f"火山引擎识别超时（>{VOLC_POLL_TIMEOUT:.0f}s），任务仍在处理中")
            time.sleep(VOLC_POLL_INTERVAL)
    finally:
        cleanup_oss(bucket, oss_key)

    result = body.get("result") or {}
    utterances = result.get("utterances") or []
    if not utterances:
        text = result.get("text", "")
        if not text:
            raise TranscribeError("火山引擎响应中没有识别结果")
        return [{"start_ms": 0, "end_ms": 0, "speaker": "", "text": text}]

    return [
        {
            "start_ms": int(u.get("start_time") or 0),
            "end_ms": int(u.get("end_time") or 0),
            "speaker": str((u.get("additions") or {}).get("speaker", "")),
            "text": (u.get("text") or "").strip(),
        }
        for u in utterances
        if (u.get("text") or "").strip()
    ]


# ──────────────────────────── 渲染 ────────────────────────────

def render(rows: list[dict], plain: bool) -> str:
    has_ts = any(r["end_ms"] > 0 for r in rows)
    if plain or not has_ts:
        return "\n".join(r["text"] for r in rows if r["text"])

    speakers = len({r["speaker"] for r in rows if r["speaker"]}) > 1
    lines = []
    for r in rows:
        if not r["text"]:
            continue
        s = r["start_ms"] // 1000
        prefix = f"[{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}]"
        if speakers and r["speaker"]:
            prefix += f" S{r['speaker']}"
        lines.append(f"{prefix}  {r['text']}")
    return "\n".join(lines)


# ──────────────────────────── 主流程 ────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="音频/视频转文字")
    ap.add_argument("input", help="音频或视频文件")
    ap.add_argument("output", nargs="?", help="输出 txt；省略则打到 stdout")
    ap.add_argument("--plain", action="store_true", help="只输出纯文本，去掉时间戳/说话人")
    args = ap.parse_args()

    src = Path(args.input).expanduser()
    if not src.is_file():
        print(f"error: 文件不存在: {src}", file=sys.stderr)
        return 1

    try:
        require_ffmpeg()
        key = api_key("VOLCENGINE_ASR_APP_KEY")

        workdir = Path(tempfile.mkdtemp(prefix="transcribe-"))
        try:
            audio = normalize(src, workdir)
            rows = volcengine_transcribe(audio, key)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        if not rows:
            raise TranscribeError("转写结果为空")

        text = render(rows, args.plain)
    except TranscribeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.output:
        out = Path(args.output).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"saved to {out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
