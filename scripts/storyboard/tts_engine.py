#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tts_engine.py — 可插拔 TTS 後端封裝 (v1.0)

用途：
把原本硬寫在 assemble_episode.py 內的 Edge-TTS / Windows SAPI 配音流程抽成獨立模組，
並支援可插拔後端（本專案預設用本機 VoiceStudio）：

  * voicestudio   — 本機 VoiceStudio / OmniVoice voicebox API (http://127.0.0.1:8001)
  * fish          — Fish Audio 雲端 (dialect=fish_cloud) 或本機 OpenAI 相容 fish-speech (dialect=fish_local)
  * openai_compat — 自帶 API：任何 OpenAI 相容的 /v1/audio/speech 端點
  * sapi          — Windows 原生 SAPI（PowerShell），完全離線
  * edge          — edge-tts（2026-10-10 起回 403 且非商用授權，僅供離線除錯）

設計原則：
  * 只用標準函式庫（urllib.request / pathlib / subprocess），不新增任何 pip 相依，Python >= 3.10。
  * 設定檔缺席時必須優雅降級：模組可匯入、discover 仍可列出演擎、synthesize 會明確回報失敗原因。
  * 金鑰永不寫入日誌、永不印出；所有錯誤訊息一律遮罩（redact）。
  * 產出音訊一律正規化成 48 kHz 單聲道 WAV，方便後段 FFmpeg 混音與時間軸對齊。
  * 呼叫端全程無 shell=True，所有子行程皆以 argv 陣列呼叫。

設定檔（config/tts.json，已 git-ignore；可另存 config/tts.example.json 當範例）：

  {
    "default_engine": "voicestudio",
    "engines": {
      "voicestudio": {"base_url": "http://127.0.0.1:8001", "timeout_sec": 180,
                      "default_profile": "", "default_voice_engine": "qwen", "default_language": "zh"},
      "fish": {"dialect": "fish_cloud", "base_url": "https://api.fish.audio", "api_key": "",
               "model": "speech-1.6", "voice_id": "", "reference_id": "", "format": "mp3"},
      "openai_compat": {"base_url": "", "api_key": "", "model": "", "voice": "", "response_format": "wav",
                        "auth_header": "Authorization", "auth_prefix": "Bearer ", "headers": {}, "extra_body": {}}
    },
    "voice_map": {"V-narrator": "角色A｜冷面上班族內心旁白 V2", "V-lin-zhao": "阿廷AI聲"}
  }

CLI：
  python scripts/storyboard/tts_engine.py --doctor
  python scripts/storyboard/tts_engine.py --list-voices --engine voicestudio
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as urlerror
from urllib import request as urlrequest

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ==============================================================================
# 常數
# ==============================================================================

DEFAULT_CONFIG_NAME = "tts.json"

PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: engine="auto" 時的優先序（第一個可用者勝出）。
AUTO_ENGINE_ORDER: Tuple[str, ...] = ("voicestudio", "fish", "openai_compat", "sapi")

#: discover_engines / doctor 的固定列舉順序。
ALL_ENGINE_IDS: Tuple[str, ...] = ("voicestudio", "fish", "openai_compat", "sapi", "edge")

ENGINE_LABELS: Dict[str, str] = {
    "voicestudio": "VoiceStudio／OmniVoice（本機 voicebox API）",
    "fish": "Fish Audio／fish-speech",
    "openai_compat": "自帶 API（OpenAI 相容 /v1/audio/speech）",
    "sapi": "Windows 原生 SAPI（離線）",
    "edge": "edge-tts（已故障／非商用）",
}

#: 目標音訊規格：下游 FFmpeg 混音一律吃 48 kHz 單聲道 WAV。
TARGET_SAMPLE_RATE = 48000
TARGET_CHANNELS = 1

#: 已知的音訊檔 magic bytes（用來判斷 /audio/{id} 回來的是二進位還是 JSON）。
AUDIO_MAGIC: Tuple[bytes, ...] = (
    b"RIFF",       # WAV
    b"ID3",        # MP3 (with ID3)
    b"OggS",       # OGG / Opus
    b"fLaC",       # FLAC
    b"\xff\xfb",   # MP3
    b"\xff\xf3",   # MP3
    b"\xff\xf2",   # MP3
    b"\x1a\x45\xdf\xa3",  # Matroska / WebM
)

#: ffmpeg 不在 PATH 時的已知安裝位置（WinGet Gyan 套件）。
FFMPEG_KNOWN_PATHS: Tuple[str, ...] = (
    "C:\\Users\\kirit\\AppData\\Local\\Microsoft\\WinGet\\Packages\\"
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg-9.0.2-full_build\\bin\\ffmpeg.exe",
)

#: 文字長度上限（對齊各供應商 API 的限制；/speak 為 10000、/generate 為 50000）。
MAX_TEXT_CHARS = 10000

#: 遮罩後取代金鑰的字樣。
REDACTED = "***REDACTED***"

_SECRET_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[^\s\"',;]+"),
    re.compile(r"\bsk-[A-Za-z0-9._\-]{6,}"),
    re.compile(r"(?i)(\"?(?:api[_-]?key|apikey|token|secret)\"?\s*[:=]\s*\"?)([^\s\"',}]{4,})"),
)


# ==============================================================================
# 例外與 HTTP 傳輸層
# ==============================================================================

class TtsError(RuntimeError):
    """TTS 流程的可預期失敗（連線錯誤、供應商拒絕、格式不符…），訊息已遮罩。"""


class _HttpResponse:
    """最小 HTTP 回應容器：狀態碼、標頭、原始位元組。"""

    __slots__ = ("status", "headers", "body")

    def __init__(self, status: int, headers: Optional[Dict[str, str]] = None, body: bytes = b""):
        self.status = int(status)
        self.headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
        self.body = body or b""

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").lower()

    def text(self, limit: int = 400) -> str:
        """把回應體轉成可讀字串（截斷），供錯誤訊息使用。"""
        raw = self.body[: limit * 4]
        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TtsError(f"回應不是合法 JSON: {exc}") from exc


def _default_transport(method: str, url: str, headers: Optional[Dict[str, str]] = None,
                       body: Optional[bytes] = None, timeout: float = 30.0) -> _HttpResponse:
    """預設 HTTP 傳輸：以 urllib.request 實作，永遠帶逾時。"""
    request = urlrequest.Request(url, data=body, method=method.upper())
    for key, value in (headers or {}).items():
        request.add_header(str(key), str(value))
    try:
        with urlrequest.urlopen(request, timeout=timeout) as response:
            return _HttpResponse(response.status, dict(response.headers.items()), response.read())
    except urlerror.HTTPError as exc:            # 4xx/5xx：仍要取回內文當錯誤訊息
        payload = b""
        try:
            payload = exc.read() or b""
        except Exception:                         # pragma: no cover - 讀不到內文不致命
            payload = b""
        headers_map = dict(exc.headers.items()) if exc.headers else {}
        return _HttpResponse(exc.code, headers_map, payload)
    except urlerror.URLError as exc:
        raise TtsError(f"無法連線 {url}：{exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise TtsError(f"連線 {url} 失敗：{exc}") from exc


#: 測試注入點：把這個模組級別名換掉即可攔截所有 HTTP 呼叫。
#: 簽章為 transport(method, url, headers=None, body=None, timeout=30.0) -> _HttpResponse
HTTP_TRANSPORT = _default_transport


def _http_request(method: str, url: str, *, headers: Optional[Dict[str, str]] = None,
                  body: Optional[bytes] = None, timeout: float = 30.0) -> _HttpResponse:
    """走可注入的傳輸層發出請求。"""
    transport = HTTP_TRANSPORT
    return transport(method, url, headers=dict(headers or {}), body=body, timeout=float(timeout))


# ==============================================================================
# 遮罩（redaction）
# ==============================================================================

def redact_secrets(text: Any, secrets: Tuple[str, ...] = ()) -> str:
    """把金鑰樣式的片段從文字中遮罩掉；可額外指定要遮罩的字面值。"""
    result = str(text if text is not None else "")
    for secret in secrets:
        candidate = str(secret)
        if len(candidate) >= 4:
            result = result.replace(candidate, REDACTED)
    result = _SECRET_PATTERNS[0].sub(f"Bearer {REDACTED}", result)
    result = _SECRET_PATTERNS[1].sub(f"sk-{REDACTED}", result)
    result = _SECRET_PATTERNS[2].sub(lambda m: f"{m.group(1)}{REDACTED}", result)
    return result


def _engine_secrets(engine_cfg: Dict[str, Any]) -> Tuple[str, ...]:
    """收集此引擎設定中所有可視為密鑰的字串，供錯誤訊息遮罩。"""
    secrets: List[str] = []
    for key in ("api_key", "token", "secret"):
        value = engine_cfg.get(key)
        if isinstance(value, str) and value.strip():
            secrets.append(value.strip())
    env_name = str(engine_cfg.get("api_key_env") or "").strip()
    if env_name:
        env_value = os.environ.get(env_name)
        if env_value:
            secrets.append(env_value.strip())
    headers = engine_cfg.get("headers")
    if isinstance(headers, dict):
        for value in headers.values():
            if isinstance(value, str) and len(value.strip()) >= 8:
                secrets.append(value.strip())
    return tuple(secrets)


def _fail(engine_cfg: Dict[str, Any], message: str) -> TtsError:
    """建立已遮罩的錯誤。"""
    return TtsError(redact_secrets(message, _engine_secrets(engine_cfg or {})))


# ==============================================================================
# 設定檔
# ==============================================================================

def _strip_version_suffix(base_url: str) -> str:
    """去掉 base_url 尾端的 /v1，避免與 /v1/xxx 路徑疊成 /v1/v1/xxx。"""
    value = str(base_url or "").strip().rstrip("/")
    if value.lower().endswith("/v1"):
        value = value[: -len("/v1")]
    return value.rstrip("/")


def _config_candidates() -> List[Path]:
    """設定檔搜尋順序：目前工作目錄 → 專案根目錄。"""
    candidates: List[Path] = []
    try:
        candidates.append(Path.cwd() / "config" / DEFAULT_CONFIG_NAME)
    except OSError:                                  # pragma: no cover - 極少見
        pass
    candidates.append(PROJECT_ROOT / "config" / DEFAULT_CONFIG_NAME)
    return candidates


def normalise_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把設定整理成固定形狀：補預設值、剝掉重複的 /v1 後綴、清理 voice_map。"""
    result: Dict[str, Any] = copy.deepcopy(config) if isinstance(config, dict) else {}
    engines = result.get("engines")
    if not isinstance(engines, dict):
        engines = {}
    result["engines"] = engines
    result.setdefault("default_engine", "voicestudio")

    voice_map = result.get("voice_map")
    if not isinstance(voice_map, dict):
        voice_map = {}
    result["voice_map"] = {str(k): str(v) for k, v in voice_map.items() if str(v or "").strip()}

    # voicestudio
    vs = engines.get("voicestudio")
    vs = dict(vs) if isinstance(vs, dict) else {}
    vs.setdefault("base_url", "http://127.0.0.1:8001")
    vs["base_url"] = str(vs.get("base_url") or "").strip().rstrip("/")
    vs.setdefault("timeout_sec", 180)
    vs.setdefault("default_profile", "")
    vs.setdefault("default_voice_engine", "qwen")
    vs.setdefault("default_language", "zh")
    engines["voicestudio"] = vs

    # fish
    fish = engines.get("fish")
    fish = dict(fish) if isinstance(fish, dict) else {}
    fish.setdefault("dialect", "fish_cloud")
    fish.setdefault("base_url", "https://api.fish.audio")
    fish["base_url"] = str(fish.get("base_url") or "").strip().rstrip("/")
    fish.setdefault("model", "speech-1.6")
    fish.setdefault("format", "mp3")
    engines["fish"] = fish

    # openai_compat
    compat = engines.get("openai_compat")
    compat = dict(compat) if isinstance(compat, dict) else {}
    compat["base_url"] = _strip_version_suffix(compat.get("base_url") or "")
    compat.setdefault("model", "")
    compat.setdefault("voice", "")
    compat.setdefault("response_format", "wav")
    compat.setdefault("auth_header", "Authorization")
    compat.setdefault("auth_prefix", "Bearer ")
    if not isinstance(compat.get("headers"), dict):
        compat["headers"] = {}
    if not isinstance(compat.get("extra_body"), dict):
        compat["extra_body"] = {}
    engines["openai_compat"] = compat

    return result


def locate_config(config_path: Optional[str] = None) -> Optional[Path]:
    """回傳實際會被讀取的設定檔路徑；找不到回 None。

    搜尋順序：明確指定路徑 → <cwd>/config/tts.json → <專案根目錄>/config/tts.json
    """
    candidates: List[Path] = []
    if config_path:
        candidates.append(Path(config_path).expanduser())
    candidates.extend(_config_candidates())
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """讀取 TTS 設定檔；找不到或壞掉時回傳 {}（絕不拋例外）。

    搜尋順序：明確指定路徑 → <cwd>/config/tts.json → <專案根目錄>/config/tts.json
    """
    candidate = locate_config(config_path)
    if candidate is None:
        return {}
    try:
        with candidate.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return {}
    if isinstance(payload, dict):
        return normalise_config(payload)
    return {}


def _engine_config(config: Optional[Dict[str, Any]], engine_id: str) -> Dict[str, Any]:
    """取得單一引擎的設定（已正規化）。"""
    engines = (config or {}).get("engines") or {}
    section = engines.get(engine_id)
    if not isinstance(section, dict):
        section = {}
    merged = normalise_config({"engines": {engine_id: section}}).get("engines", {}).get(engine_id, {})
    return dict(merged)


def _resolve_api_key(engine_cfg: Dict[str, Any]) -> str:
    """金鑰來源：設定檔 api_key 優先，其次是設定檔指定的環境變數 api_key_env。"""
    direct = str(engine_cfg.get("api_key") or "").strip()
    if direct:
        return direct
    env_name = str(engine_cfg.get("api_key_env") or "").strip()
    if env_name:
        return str(os.environ.get(env_name) or "").strip()
    return ""


def _join_url(base_url: str, path: str) -> str:
    """拼接網址：base 尾端的 /v1 會被吸收，避免 /v1/v1 疊加。"""
    base = str(base_url or "").strip().rstrip("/")
    if path.startswith("/v1/") and base.lower().endswith("/v1"):
        base = base[: -len("/v1")]
    elif path == "/v1" and base.lower().endswith("/v1"):
        base = base[: -len("/v1")]
    return f"{base}{path}"


# ==============================================================================
# 外部工具（ffmpeg / ffprobe / nvidia-smi）
# ==============================================================================

def _find_tool(name: str) -> Optional[str]:
    """尋找外部執行檔；ffmpeg 額外試探已知的 WinGet 安裝路徑。"""
    found = shutil.which(name)
    if found:
        return found
    if name == "ffmpeg":
        for candidate in FFMPEG_KNOWN_PATHS:
            if Path(candidate).is_file():
                return candidate
    return None


def _tool_version(path: str) -> str:
    """取得外部工具版本字串（失敗回空字串）。"""
    flag = "-version" if Path(path).suffix.lower() != ".exe" else "-version"
    try:
        result = subprocess.run([path, flag], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    first = (result.stdout or "").splitlines()
    return first[0].strip() if first else ""


def _read_gpu_status() -> Dict[str, Any]:
    """讀取 nvidia-smi 的顯存用量（用於 OmniVoice 與 ComfyUI 的顯存衝突判斷）。"""
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"available": False, "reason": "找不到 nvidia-smi（可能不是 NVIDIA 顯示卡或未安裝驅動）", "gpus": []}
    command = [executable, "--query-gpu=name,memory.total,memory.used,memory.free",
               "--format=csv,noheader,nounits"]
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "reason": f"nvidia-smi 執行失敗：{exc}", "gpus": []}
    if result.returncode != 0:
        return {"available": False, "reason": (result.stderr or "nvidia-smi 執行失敗").strip()[:200], "gpus": []}
    gpus: List[Dict[str, Any]] = []
    for line in (result.stdout or "").splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        gpus.append({
            "name": parts[0],
            "total_mb": _to_int(parts[1]),
            "used_mb": _to_int(parts[2]),
            "free_mb": _to_int(parts[3]) if len(parts) > 3 else None,
        })
    return {"available": bool(gpus), "reason": "" if gpus else "nvidia-smi 沒有回報任何 GPU", "gpus": gpus}


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ==============================================================================
# 音訊：量測與正規化
# ==============================================================================

def _read_wav_header(path: Path) -> Dict[str, Any]:
    """直接讀 WAV 標頭取得時長／取樣率／聲道（沒有 ffprobe 時的後備）。"""
    try:
        with wave.open(str(path), "rb") as stream:
            rate = stream.getframerate()
            channels = stream.getnchannels()
            frames = stream.getnframes()
    except (OSError, wave.Error, EOFError):
        return {}
    duration = (frames / float(rate)) if rate else None
    return {"duration_sec": duration, "sample_rate": rate or None, "channels": channels or None}


def _probe_audio(path: Path) -> Dict[str, Any]:
    """量測音訊：ffprobe 優先，缺 ffprobe 或 ffprobe 失敗時改讀 WAV 標頭。"""
    info: Dict[str, Any] = {"duration_sec": None, "sample_rate": None, "channels": None, "codec": None}
    ffprobe = _find_tool("ffprobe")
    if ffprobe:
        command = [ffprobe, "-v", "error", "-show_entries",
                   "format=duration:stream=codec_type,codec_name,sample_rate,channels",
                   "-of", "json", str(path)]
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=60)
            data = json.loads(result.stdout or "{}")
            streams = [s for s in (data.get("streams") or []) if s.get("codec_type") == "audio"]
            if streams:
                info["sample_rate"] = _to_int(streams[0].get("sample_rate"))
                info["channels"] = _to_int(streams[0].get("channels"))
                info["codec"] = streams[0].get("codec_name")
            info["duration_sec"] = _to_float((data.get("format") or {}).get("duration"))
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    if info["duration_sec"] is None or info["sample_rate"] is None or info["channels"] is None:
        header = _read_wav_header(path)
        for key in ("duration_sec", "sample_rate", "channels"):
            if info.get(key) is None and header.get(key) is not None:
                info[key] = header[key]
    return info


def _normalise_audio(raw_path: Path, out_path: Path) -> Dict[str, Any]:
    """把供應商回傳的音訊正規化成 48 kHz 單聲道 WAV（輸出路徑決定實際格式）。

    回傳 {"converted": bool, "reason": str, "format": str}。
    找不到 ffmpeg 或轉檔失敗時，保留原始音訊（不讓整條流程失敗）。
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = out_path.suffix.lower()
    target = {".wav": ("wav", ["-c:a", "pcm_s16le"]),
              ".mp3": ("mp3", ["-c:a", "libmp3lame"]),
              ".m4a": ("m4a", ["-c:a", "aac"]),
              ".aac": ("aac", ["-c:a", "aac"])}.get(suffix, ("wav", ["-c:a", "pcm_s16le"]))

    ffmpeg = _find_tool("ffmpeg")
    if not ffmpeg:
        shutil.copyfile(raw_path, out_path)
        return {"converted": False, "reason": "找不到 ffmpeg，未做 48 kHz 單聲道正規化", "format": target[0]}

    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw_path),
               "-ac", str(TARGET_CHANNELS), "-ar", str(TARGET_SAMPLE_RATE)] + target[1] + [str(out_path)]
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=900)
    except (OSError, subprocess.SubprocessError) as exc:
        shutil.copyfile(raw_path, out_path)
        return {"converted": False, "reason": f"ffmpeg 轉檔例外：{exc}", "format": target[0]}
    if result.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        shutil.copyfile(raw_path, out_path)
        return {"converted": False, "reason": f"ffmpeg 轉檔失敗：{(result.stderr or '')[:200]}",
                "format": target[0]}
    return {"converted": True, "reason": "", "format": target[0]}


def _looks_like_audio(data: bytes) -> bool:
    """判斷回應是否為音訊二進位（依 magic bytes）。"""
    if not data:
        return False
    for magic in AUDIO_MAGIC:
        if data.startswith(magic):
            return True
    return False


# ==============================================================================
# 文字與音色處理
# ==============================================================================

def _sanitize_text(text: Any) -> str:
    """清理要送進 TTS 的文字：移除控制字元、壓縮空白，保留標點。"""
    value = str(text if text is not None else "")
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _resolve_voice(speaker: str, voice: Optional[str], config: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    """解析要送給供應商的音色。

    順序：明確指定的 voice → config["voice_map"][speaker] → speaker 原文（可能是自由 profile 名稱）。
    回傳 (音色值, 來源說明)。
    """
    if voice:
        return str(voice), "explicit"
    voice_map = (config or {}).get("voice_map") or {}
    key = str(speaker or "").strip()
    if key and key in voice_map:
        return str(voice_map[key]), "voice_map"
    if key:
        return key, "speaker"
    return "", "none"


# ==============================================================================
# VoiceStudio / OmniVoice voicebox API
# ==============================================================================

def _vs_base_url(engine_cfg: Dict[str, Any]) -> str:
    return str(engine_cfg.get("base_url") or "http://127.0.0.1:8001").rstrip("/")


def _vs_timeout(engine_cfg: Dict[str, Any]) -> float:
    value = _to_float(engine_cfg.get("timeout_sec"))
    return value if value and value > 0 else 180.0


def _vs_fetch_profiles(engine_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """GET /profiles；失敗回空清單（不拋例外，讓呼叫端有後備值）。"""
    try:
        response = _http_request("GET", f"{_vs_base_url(engine_cfg)}/profiles",
                                 timeout=min(_vs_timeout(engine_cfg), 30.0))
    except TtsError:
        return []
    if response.status >= 400:
        return []
    try:
        payload = response.json()
    except TtsError:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("profiles", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _vs_find_profile(profiles: List[Dict[str, Any]], voice: str) -> Optional[Dict[str, Any]]:
    """以名稱或 id 找到對應的 voice profile。"""
    if not voice:
        return None
    for profile in profiles:
        if str(profile.get("id") or "") == voice:
            return profile
    for profile in profiles:
        if str(profile.get("name") or "") == voice:
            return profile
    return None


def _vs_status_payload(response: _HttpResponse) -> Dict[str, Any]:
    """解析 /generate/{id}/status；該端點可能回 JSON，也可能回 SSE（data: ...）。"""
    text = response.text(limit=8000)
    stripped = text.strip()
    if stripped.startswith("data:") or stripped.startswith("event:"):
        last = ""
        for line in stripped.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload and payload != "[DONE]":
                    last = payload
        if last:
            try:
                parsed = json.loads(last)
                return parsed if isinstance(parsed, dict) else {"value": parsed}
            except json.JSONDecodeError:
                return {"raw": stripped[:400]}
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return {"raw": stripped[:400]}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


_TERMINAL_OK = {"completed", "complete", "success", "succeeded", "done", "ready", "finished"}
_TERMINAL_FAIL = {"failed", "error", "cancelled", "canceled", "aborted"}


def _vs_wait_for_generation(engine_cfg: Dict[str, Any], generation_id: str) -> Dict[str, Any]:
    """輪詢 /generate/{id}/status 直到完成或逾時。"""
    timeout = _vs_timeout(engine_cfg)
    deadline = time.monotonic() + timeout
    url = f"{_vs_base_url(engine_cfg)}/generate/{generation_id}/status"
    last: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = _http_request("GET", url, timeout=min(timeout, 60.0))
        if response.status >= 400:
            raise _fail(engine_cfg, f"查詢生成狀態失敗：HTTP {response.status} {response.text(200)}")
        last = _vs_status_payload(response)
        status = str(last.get("status") or "").strip().lower()
        if status in _TERMINAL_OK:
            return last
        if status in _TERMINAL_FAIL:
            raise _fail(engine_cfg, f"VoiceStudio 生成失敗：{last.get('error') or status}")
        time.sleep(1.5)
    raise _fail(engine_cfg, f"等待 VoiceStudio 生成音訊逾時（{timeout:.0f} 秒）")


def _vs_download_audio(engine_cfg: Dict[str, Any], generation_id: str) -> bytes:
    """GET /audio/{id}：可能是音訊二進位，也可能是含 url/path 的 JSON。"""
    url = f"{_vs_base_url(engine_cfg)}/audio/{generation_id}"
    response = _http_request("GET", url, timeout=min(_vs_timeout(engine_cfg), 300.0))
    if response.status >= 400:
        raise _fail(engine_cfg, f"取回音訊失敗：HTTP {response.status} {response.text(200)}")
    data = response.body or b""
    if _looks_like_audio(data):
        return data
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail(engine_cfg, f"無法辨識 /audio/{generation_id} 的回應格式：{exc}") from exc
    if isinstance(payload, dict):
        for key in ("url", "audio_url", "file_url", "path", "audio_path", "file", "download_url"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return _vs_fetch_remote_audio(engine_cfg, value.strip())
    raise _fail(engine_cfg, f"/audio/{generation_id} 回應不含可用的音訊或網址")


def _vs_fetch_remote_audio(engine_cfg: Dict[str, Any], url: str) -> bytes:
    """下載 JSON 內指向的音訊檔（相對網址以 VoiceStudio 主機補齊）。"""
    if url.startswith("/"):
        url = f"{_vs_base_url(engine_cfg)}{url}"
    response = _http_request("GET", url, timeout=min(_vs_timeout(engine_cfg), 300.0))
    if response.status >= 400:
        raise _fail(engine_cfg, f"下載音訊檔失敗：HTTP {response.status}")
    if not _looks_like_audio(response.body or b""):
        raise _fail(engine_cfg, "下載到的音訊格式無法辨識")
    return response.body


def _synth_voicestudio(text: str, out_path: Path, *, voice: str, language: Optional[str],
                        engine_cfg: Dict[str, Any], extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """VoiceStudio / OmniVoice：POST /speak（或 /generate）→ 等待完成 → GET /audio/{id}。"""
    base_url = _vs_base_url(engine_cfg)
    timeout = _vs_timeout(engine_cfg)
    profiles = _vs_fetch_profiles(engine_cfg)
    profile = _vs_find_profile(profiles, voice)
    if profile is None and engine_cfg.get("default_profile"):
        profile = _vs_find_profile(profiles, str(engine_cfg.get("default_profile")))
        if profile is not None:
            voice = str(profile.get("name") or voice)

    # 引擎選擇：profile 自己的 default_engine 優先，其次才是設定檔的 default_voice_engine。
    voice_engine = str(engine_cfg.get("voice_engine") or "").strip()
    if not voice_engine and profile is not None:
        voice_engine = str(profile.get("default_engine") or "").strip()
    if not voice_engine:
        voice_engine = str(engine_cfg.get("default_voice_engine") or "").strip()

    # personality：設定檔明確指定優先；否則看 profile 有沒有 personality 提示。
    personality = engine_cfg.get("personality")
    if personality is None:
        personality = bool(profile.get("personality")) if profile is not None else None

    effective_language = str(language or engine_cfg.get("default_language") or "zh").strip() or "zh"

    mode = str(engine_cfg.get("mode") or "speak").strip().lower()
    payload: Dict[str, Any] = {"text": text, "language": effective_language}
    if voice_engine:
        payload["engine"] = voice_engine
    if personality is not None:
        payload["personality"] = bool(personality)
    if extra:
        payload.update(extra)

    if mode == "generate":
        profile_id = str(profile.get("id") or voice or "").strip()
        if not profile_id:
            raise _fail(engine_cfg, "VoiceStudio /generate 需要 profile_id，但找不到對應的 voice profile")
        body = {
            "profile_id": profile_id,
            "text": text,
            "language": effective_language,
            "engine": voice_engine or "qwen",
            "personality": bool(personality),
        }
        if extra:
            body.update(extra)
        body["profile_id"] = profile_id          # 音色解析結果優先於 extra
        body["text"] = text
        response = _http_request("POST", f"{base_url}/generate",
                                 headers={"Content-Type": "application/json"},
                                 body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 timeout=timeout)
    else:
        if voice:
            payload["profile"] = voice
        payload["text"] = text                  # 文字與音色解析結果優先於 extra
        response = _http_request("POST", f"{base_url}/speak",
                                 headers={"Content-Type": "application/json"},
                                 body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 timeout=timeout)

    if response.status >= 400:
        raise _fail(engine_cfg, f"VoiceStudio 回應 HTTP {response.status}：{response.text(300)}")
    try:
        result = response.json()
    except TtsError as exc:
        raise _fail(engine_cfg, f"VoiceStudio 回應不是合法 JSON：{exc}") from exc
    if not isinstance(result, dict):
        raise _fail(engine_cfg, "VoiceStudio 回應格式異常（不是 JSON 物件）")

    status = str(result.get("status") or "completed").strip().lower()
    generation_id = str(result.get("id") or "").strip()
    if status in _TERMINAL_FAIL:
        raise _fail(engine_cfg, f"VoiceStudio 生成失敗：{result.get('error') or status}")
    if status not in _TERMINAL_OK and generation_id:
        result = _vs_wait_for_generation(engine_cfg, generation_id)
        status = str(result.get("status") or "completed").strip().lower()
    if not generation_id:
        generation_id = str(result.get("id") or "").strip()
    if not generation_id:
        raise _fail(engine_cfg, "VoiceStudio 回應沒有 generation id，無法取回音訊")

    audio = _vs_download_audio(engine_cfg, generation_id)

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as handle:
        handle.write(audio)
        temp_path = Path(handle.name)
    try:
        conversion = _normalise_audio(temp_path, out_path)
    finally:
        temp_path.unlink(missing_ok=True)

    return {
        "provider": "voicestudio",
        "endpoint": f"{base_url}/{'generate' if mode == 'generate' else 'speak'}",
        "generation_id": generation_id,
        "status": status,
        "profile": voice,
        "voice_engine": voice_engine,
        "language": effective_language,
        "duration_hint": result.get("duration"),
        "conversion": conversion,
        "response": result,
    }


# ==============================================================================
# Fish Audio / fish-speech
# ==============================================================================

def _synth_fish(text: str, out_path: Path, *, voice: str, language: Optional[str],
                engine_cfg: Dict[str, Any], extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Fish Audio：依 dialect 走雲端 /v1/tts 或本機 OpenAI 相容 /v1/audio/speech。"""
    dialect = str(engine_cfg.get("dialect") or "fish_cloud").strip().lower()
    base_url = str(engine_cfg.get("base_url") or "").strip().rstrip("/")
    api_key = _resolve_api_key(engine_cfg)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    if dialect == "fish_local":
        body: Dict[str, Any] = {
            "model": str(engine_cfg.get("model") or ""),
            "input": text,
            "voice": str(engine_cfg.get("voice_id") or voice or ""),
            "response_format": str(engine_cfg.get("format") or "wav"),
        }
        if language:
            body["language"] = language
        if extra:
            body.update(extra)
        response = _http_request("POST", _join_url(base_url, "/v1/audio/speech"),
                                 headers=headers,
                                 body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 timeout=180.0)
        if response.status >= 400:
            raise _fail(engine_cfg, f"fish_local 回應 HTTP {response.status}：{response.text(300)}")
        audio = response.body
        if not audio:
            raise _fail(engine_cfg, "fish_local 回應沒有音訊內容")
        payload_summary = {"dialect": dialect, "endpoint": _join_url(base_url, "/v1/audio/speech")}
    else:
        body = {
            "text": text,
            "format": str(engine_cfg.get("format") or "mp3"),
            "model": str(engine_cfg.get("model") or "speech-1.6"),
        }
        reference_id = str(engine_cfg.get("reference_id") or "").strip()
        voice_id = str(engine_cfg.get("voice_id") or "").strip() or (voice if not reference_id else "")
        if reference_id:
            body["reference_id"] = reference_id
        elif voice_id:
            body["voice_id"] = voice_id
        if extra:
            body.update(extra)
        if not api_key:
            raise _fail(engine_cfg, "fish_cloud 需要 API 金鑰（設定 api_key 或 api_key_env）")
        response = _http_request("POST", _join_url(base_url, "/v1/tts"),
                                 headers=headers,
                                 body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 timeout=180.0)
        if response.status >= 400:
            raise _fail(engine_cfg, f"fish_cloud 回應 HTTP {response.status}：{response.text(300)}")
        try:
            result = response.json()
        except TtsError as exc:
            raise _fail(engine_cfg, f"fish_cloud 回應不是合法 JSON：{exc}") from exc
        url = ""
        if isinstance(result, dict):
            for key in ("url", "audio_url", "download_url"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    url = value.strip()
                    break
        if not url:
            raise _fail(engine_cfg, "fish_cloud 回應沒有 url 欄位，無法下載音訊")
        download = _http_request("GET", url, timeout=300.0)
        if download.status >= 400:
            raise _fail(engine_cfg, f"下載 fish 音訊失敗：HTTP {download.status}")
        audio = download.body
        payload_summary = {"dialect": dialect, "endpoint": _join_url(base_url, "/v1/tts"),
                           "audio_url": url, "response": result}

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as handle:
        handle.write(audio)
        temp_path = Path(handle.name)
    try:
        conversion = _normalise_audio(temp_path, out_path)
    finally:
        temp_path.unlink(missing_ok=True)

    payload_summary.update({"provider": "fish", "conversion": conversion, "voice": voice})
    return payload_summary


# ==============================================================================
# 自帶 API（OpenAI 相容）
# ==============================================================================

def _synth_openai_compat(text: str, out_path: Path, *, voice: str, language: Optional[str],
                         engine_cfg: Dict[str, Any], extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """自帶 API：POST {base_url}/v1/audio/speech，回應音訊二進位。"""
    base_url = str(engine_cfg.get("base_url") or "").strip()
    if not base_url:
        raise _fail(engine_cfg, "openai_compat 尚未設定 base_url")
    model = str(engine_cfg.get("model") or "").strip()
    if not model:
        raise _fail(engine_cfg, "openai_compat 尚未設定 model")

    auth_header = str(engine_cfg.get("auth_header") or "Authorization")
    auth_prefix = engine_cfg.get("auth_prefix")
    auth_prefix = "Bearer " if auth_prefix is None else str(auth_prefix)
    api_key = _resolve_api_key(engine_cfg)

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    extra_headers = engine_cfg.get("headers")
    if isinstance(extra_headers, dict):
        for key, value in extra_headers.items():
            if value is not None:
                headers[str(key)] = str(value)
    if api_key and auth_header:
        headers[auth_header] = f"{auth_prefix}{api_key}"

    body: Dict[str, Any] = {
        "model": model,
        "input": text,
        "voice": str(engine_cfg.get("voice") or voice or ""),
        "response_format": str(engine_cfg.get("response_format") or "wav"),
    }
    if language:
        body["language"] = language
    for key in ("speed", "instructions"):
        value = engine_cfg.get(key)
        if value not in (None, ""):
            body[key] = value
    extra_body = engine_cfg.get("extra_body")
    if isinstance(extra_body, dict):
        body.update(extra_body)
    if extra:
        body.update(extra)                      # extra 最後合併，優先度最高

    endpoint = _join_url(base_url, "/v1/audio/speech")
    response = _http_request("POST", endpoint, headers=headers,
                             body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                             timeout=180.0)
    if response.status >= 400:
        raise _fail(engine_cfg, f"openai_compat 回應 HTTP {response.status}：{response.text(300)}")
    audio = response.body
    if not audio:
        raise _fail(engine_cfg, "openai_compat 回應沒有音訊內容")
    if not _looks_like_audio(audio):
        # 有些端點仍回 JSON（例如 {"data": "base64..."}）
        try:
            payload = json.loads(audio.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict):
            import base64
            encoded = ""
            for key in ("audio", "data", "b64_json", "audio_content"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    encoded = value
                    break
            if encoded:
                try:
                    audio = base64.b64decode(encoded)
                except (ValueError, TypeError) as exc:
                    raise _fail(engine_cfg, f"openai_compat 回應的 base64 音訊無法解析：{exc}") from exc
            else:
                raise _fail(engine_cfg, "openai_compat 回應不是音訊，也不是可解析的 JSON")
        else:
            raise _fail(engine_cfg, "openai_compat 回應不是音訊，也不是可解析的 JSON")

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as handle:
        handle.write(audio)
        temp_path = Path(handle.name)
    try:
        conversion = _normalise_audio(temp_path, out_path)
    finally:
        temp_path.unlink(missing_ok=True)

    return {
        "provider": "openai_compat",
        "endpoint": endpoint,
        "model": model,
        "voice": body.get("voice"),
        "response_format": body.get("response_format"),
        "conversion": conversion,
    }


# ==============================================================================
# Windows SAPI（離線）
# ==============================================================================

SAPI_PS_SCRIPT = """param ([string]$text, [string]$outFile, [string]$voice)
Add-Type -AssemblyName System.Speech
$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($voice) {
  try { $speak.SelectVoice($voice) } catch { }
}
$speak.SetOutputToWaveFile($outFile)
$speak.Speak($text)
$speak.Dispose()
"""


def _sapi_available() -> bool:
    """Windows SAPI 只在 Windows 上存在。"""
    return os.name == "nt"


def _synth_sapi(text: str, out_path: Path, *, voice: str, language: Optional[str],
                engine_cfg: Dict[str, Any], extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Windows SAPI：寫一支臨時 PowerShell 腳本產生 WAV，再正規化成 48 kHz 單聲道。"""
    if not _sapi_available():
        raise _fail(engine_cfg, "Windows SAPI 只在 Windows 上可用")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", encoding="utf-8", delete=False) as handle:
        handle.write(SAPI_PS_SCRIPT)
        script_path = Path(handle.name)
    raw_path = out_path.with_name(f".{out_path.name}.sapi.tmp")
    try:
        command = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path),
                   "-text", text, "-outFile", str(raw_path), "-voice", str(voice or "")]
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=300)
        except FileNotFoundError:
            command[0] = "pwsh"
            result = subprocess.run(command, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=300)
        if result.returncode != 0 or not raw_path.exists() or raw_path.stat().st_size <= 1000:
            raise _fail(engine_cfg, f"Windows SAPI 生成失敗：{(result.stderr or '').strip()[:200]}")
        conversion = _normalise_audio(raw_path, out_path)
    finally:
        script_path.unlink(missing_ok=True)
        raw_path.unlink(missing_ok=True)
    return {"provider": "sapi", "engine": "windows-sapi", "voice": voice, "conversion": conversion}


# ==============================================================================
# edge-tts（已故障／非商用）
# ==============================================================================

def _edge_available() -> bool:
    """edge-tts 套件是否已安裝。"""
    try:
        return importlib.util.find_spec("edge_tts") is not None
    except (ImportError, ValueError):
        return False


def _synth_edge(text: str, out_path: Path, *, voice: str, language: Optional[str],
                engine_cfg: Dict[str, Any], extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """edge-tts：保留舊路徑供離線除錯；2026-10-10 起微軟要求 Sec-MS-GEC v2 token，會回 403。"""
    try:
        import asyncio
        import edge_tts
    except ImportError as exc:
        raise _fail(engine_cfg, f"edge-tts 未安裝：{exc}") from exc
    default_voice = "zh-TW-HsiaoChenNeural" if any(
        key in str(voice or "").lower() for key in ("female", "woman", "girl", "女")) else "zh-TW-YunJheNeural"
    effective_voice = str(voice or default_voice)
    raw_path = out_path.with_name(f".{out_path.name}.edge.tmp")
    try:
        async def _run() -> None:
            communicate = edge_tts.Communicate(text, effective_voice)
            await communicate.save(str(raw_path))

        asyncio.run(_run())
        if not raw_path.exists() or raw_path.stat().st_size <= 1000:
            raise _fail(engine_cfg, "edge-tts 沒有產生有效音訊（2026-10-10 起微軟已封鎖此路徑）")
        conversion = _normalise_audio(raw_path, out_path)
    finally:
        raw_path.unlink(missing_ok=True)
    return {"provider": "edge", "voice": effective_voice, "conversion": conversion,
            "warning": "edge-tts 非商用授權且自 2026-10-10 起回 403"}


_ENGINE_SYNTH = {
    "voicestudio": _synth_voicestudio,
    "fish": _synth_fish,
    "openai_compat": _synth_openai_compat,
    "sapi": _synth_sapi,
    "edge": _synth_edge,
}


# ==============================================================================
# 對外 API
# ==============================================================================

def _voicestudio_check(engine_cfg: Dict[str, Any]) -> Tuple[bool, str, str, Dict[str, Any]]:
    """本機 VoiceStudio 伺服器是否可連線。"""
    base_url = _vs_base_url(engine_cfg)
    try:
        response = _http_request("GET", f"{base_url}/health", timeout=3.0)
    except TtsError as exc:
        return False, "VoiceStudio 伺服器未啟動", str(exc), {}
    if response.status >= 400:
        return False, f"VoiceStudio /health 回應 HTTP {response.status}", response.text(200), {}
    try:
        payload = response.json()
    except TtsError as exc:
        return False, "VoiceStudio /health 回應不是合法 JSON", str(exc), {}
    if not isinstance(payload, dict):
        return False, "VoiceStudio /health 回應格式異常", "", {}
    status = str(payload.get("status") or "").lower()
    if status and status not in {"ok", "healthy", "ready", "running", "idle"}:
        return False, f"VoiceStudio 回報狀態 {status}", "", payload
    return True, "VoiceStudio 伺服器可用", f"model_loaded={payload.get('model_loaded')}", payload


def _fish_check(engine_cfg: Dict[str, Any]) -> Tuple[bool, str, str]:
    """Fish 可用性：雲端需要金鑰；本機 dialect 需要 base_url。"""
    dialect = str(engine_cfg.get("dialect") or "fish_cloud").strip().lower()
    if dialect == "fish_local":
        base_url = str(engine_cfg.get("base_url") or "").strip()
        if not base_url:
            return False, "fish_local 需要設定 base_url", "本機 fish-speech 伺服器位址未設定"
        return True, "fish_local 已設定 base_url", base_url
    if _resolve_api_key(engine_cfg):
        return True, "Fish Audio API 金鑰已設定", ""
    return False, "Fish Audio API 金鑰未設定", "請在 config/tts.json 設定 engines.fish.api_key 或 api_key_env"


def _openai_compat_check(engine_cfg: Dict[str, Any]) -> Tuple[bool, str, str]:
    """自帶 API 可用性：base_url + model 都要有。"""
    base_url = str(engine_cfg.get("base_url") or "").strip()
    model = str(engine_cfg.get("model") or "").strip()
    if not base_url:
        return False, "openai_compat 尚未設定 base_url", "請在 config/tts.json 設定 engines.openai_compat.base_url"
    if not model:
        return False, "openai_compat 尚未設定 model", "請在 config/tts.json 設定 engines.openai_compat.model"
    return True, "openai_compat 已設定 base_url 與 model", f"{base_url}（model={model}）"


def _sapi_check() -> Tuple[bool, str, str]:
    """SAPI 可用性。"""
    if os.name != "nt":
        return False, "非 Windows 系統，沒有 Windows SAPI", "可改用 voicestudio / fish / openai_compat"
    return True, "Windows SAPI 可用（離線）", "使用 System.Speech 合成，音檔需再轉 48 kHz 單聲道"


def _edge_check() -> Tuple[bool, str, str]:
    """edge-tts 可用性：套件可安裝，但自 2026-10-10 起一律視為不可用於正式產出。"""
    installed = _edge_available()
    reason = "edge-tts 自 2026-10-10 起回 403（微軟要求 Sec-MS-GEC v2 token），且僅限非商用授權"
    if installed:
        return False, reason, "套件已安裝，僅供離線除錯；正式產出請改用 voicestudio / fish / openai_compat / sapi"
    return False, reason, "套件未安裝（pip install edge-tts）；仍不建議用於正式產出"


def _check_engine(engine_id: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """單一引擎的可用性檢查（回傳 available/reason/detail 與額外資訊）。"""
    cfg = config if isinstance(config, dict) else load_config()
    engine_cfg = _engine_config(cfg, engine_id)
    detail_extra: Dict[str, Any] = {}

    if engine_id == "voicestudio":
        available, reason, detail, health = _voicestudio_check(engine_cfg)
        detail_extra["health"] = health
        detail_extra["base_url"] = _vs_base_url(engine_cfg)
    elif engine_id == "fish":
        available, reason, detail = _fish_check(engine_cfg)
        detail_extra["dialect"] = str(engine_cfg.get("dialect") or "fish_cloud")
    elif engine_id == "openai_compat":
        available, reason, detail = _openai_compat_check(engine_cfg)
        detail_extra["base_url"] = str(engine_cfg.get("base_url") or "")
    elif engine_id == "sapi":
        available, reason, detail = _sapi_check()
    elif engine_id == "edge":
        available, reason, detail = _edge_check()
        detail_extra["package_installed"] = _edge_available()
    else:
        available, reason, detail = False, f"未知引擎 {engine_id}", ""

    return {
        "id": engine_id,
        "label": ENGINE_LABELS.get(engine_id, engine_id),
        "available": bool(available),
        "reason": reason,
        "detail": detail,
        **detail_extra,
    }


def discover_engines(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """盤點所有 TTS 引擎的可用性；回傳固定順序的清單。

    每筆至少含 {"id", "label", "available", "reason", "detail"}。
    """
    cfg = config if isinstance(config, dict) else load_config()
    return [_check_engine(engine_id, cfg) for engine_id in ALL_ENGINE_IDS]


def engine_health(engine_id: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """單一引擎的健檢結果；voicestudio 會另外讀 /health、/models/status 與 nvidia-smi。"""
    cfg = config if isinstance(config, dict) else load_config()
    if engine_id not in ALL_ENGINE_IDS:
        raise ValueError(f"未知引擎：{engine_id}")
    result = _check_engine(engine_id, cfg)
    result.setdefault("engine", engine_id)
    result["config_present"] = bool((cfg.get("engines") or {}).get(engine_id))

    if engine_id == "voicestudio":
        engine_cfg = _engine_config(cfg, engine_id)
        models: List[Dict[str, Any]] = []
        try:
            response = _http_request("GET", f"{_vs_base_url(engine_cfg)}/models/status",
                                     timeout=10.0)
            if response.status < 400:
                payload = response.json()
                raw_models = payload.get("models") if isinstance(payload, dict) else payload
                if isinstance(raw_models, list):
                    models = [item for item in raw_models if isinstance(item, dict)]
        except Exception:
            models = []
        result["models"] = models
        result["downloaded_models"] = [str(item.get("model_name")) for item in models
                                       if item.get("downloaded")]
        result["gpu"] = _read_gpu_status()
        result["warnings"] = _vram_warnings(result)
        result["next_steps"] = _next_steps(engine_id, result)

    if engine_id == "fish":
        result["warnings"] = [
            "Fish Speech 程式與權重採 Fish Audio Community License：年營收 50 萬美元以下可免費使用；"
            "若將 TTS 對外提供為託管服務，需另簽協議。"
        ]
        result["next_steps"] = _next_steps(engine_id, result)
    if engine_id == "edge":
        result["warnings"] = [
            "edge-tts 非商用授權；且自 2026-10-10 起微軟要求 Sec-MS-GEC v2 token，實際呼叫會回 403。"
        ]
        result["next_steps"] = _next_steps(engine_id, result)
    if engine_id in {"sapi", "openai_compat"}:
        result.setdefault("warnings", [])
        result["next_steps"] = _next_steps(engine_id, result)
    return result


def _vram_warnings(health: Dict[str, Any]) -> List[str]:
    """OmniVoice 與 ComfyUI 共用 8 GB 顯存的衝突警告。"""
    warnings: List[str] = []
    gpu = health.get("gpu") or {}
    if not gpu.get("available"):
        return warnings
    server_up = bool(health.get("available"))
    for item in gpu.get("gpus") or []:
        used = item.get("used_mb") or 0
        total = item.get("total_mb") or 0
        name = item.get("name") or "GPU"
        if server_up and used >= 3500:
            warnings.append(
                f"{name} 已用 {used} MB／{total} MB：ComfyUI 很可能仍佔著顯存。"
                "OmniVoice 另需 3～4 GB，兩者同時跑會毀掉聲音品質——"
                "請先關閉 ComfyUI，再執行 E:\\OmniVoice\\啟動-OmniVoice.bat。"
            )
        elif total and total <= 8192:
            warnings.append(
                f"{name} 總顯存只有 {total} MB：OmniVoice 需 3～4 GB，ComfyUI 閒置也會佔 5～7 GB，"
                "兩者不可同時執行（本模組只提醒，不會自動處理）。"
            )
    return warnings


def _next_steps(engine_id: str, health: Dict[str, Any]) -> str:
    """給使用者的具體下一步。"""
    if engine_id == "voicestudio":
        if health.get("available"):
            return "可直接使用；例如 --tts-engine voicestudio（記得先關閉 ComfyUI 釋放顯存）"
        return "雙擊 E:\\OmniVoice\\啟動-OmniVoice.bat 啟動本機伺服器（啟動前先關閉 ComfyUI），再重跑 doctor"
    if engine_id == "fish":
        if health.get("available"):
            return "可直接使用；注意 Community License 與託管服務的額外協議限制"
        return "在 config/tts.json 設定 engines.fish.api_key（或 api_key_env 指向的環境變數）"
    if engine_id == "openai_compat":
        if health.get("available"):
            return "可直接使用；建議先用 --tts-engine openai_compat 試跑一段"
        return "在 config/tts.json 設定 engines.openai_compat.base_url 與 model"
    if engine_id == "sapi":
        if health.get("available"):
            return "可直接使用（離線備援，音檔會自動轉 48 kHz 單聲道）"
        return "目前不是 Windows 或 PowerShell 不可用，請改用 voicestudio / fish / openai_compat"
    if engine_id == "edge":
        return "不建議使用；請改用 voicestudio、fish、openai_compat 或 sapi"
    return ""


def _select_engines(engine: str, config: Optional[Dict[str, Any]]) -> List[str]:
    """決定要用哪些引擎；auto 取第一個可用者，指定引擎則只試該引擎。"""
    requested = str(engine or "auto").strip().lower()
    if requested and requested != "auto":
        return [requested]
    available = {item["id"]: item["available"] for item in discover_engines(config)}
    return [engine_id for engine_id in AUTO_ENGINE_ORDER if available.get(engine_id)]


def synthesize(text: str, out_path: str | Path, *, engine: str = "auto", speaker: str = "",
               voice: str | None = None, language: str | None = None,
               config: Optional[Dict[str, Any]] = None,
               extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """合成語音並寫出音訊檔。

    回傳 {"ok", "engine", "path", "duration_sec", "sample_rate", "channels", "reason", "engine_payload"}。
    engine="auto" 時依 voicestudio → fish → openai_compat → sapi 順序挑第一個可用者，
    若實際呼叫失敗會自動往下一順位補。speaker 會先經 config["voice_map"] 解析成供應商音色。
    """
    cfg = config if isinstance(config, dict) else load_config()
    out = Path(out_path)
    requested_engine = str(engine or "auto").strip().lower() or "auto"

    clean = _sanitize_text(text)
    if not clean:
        return {"ok": False, "engine": "", "path": None, "duration_sec": None,
                "sample_rate": None, "channels": None, "reason": "沒有可合成的文字內容",
                "engine_payload": {}}
    truncated = False
    if len(clean) > MAX_TEXT_CHARS:
        clean = clean[:MAX_TEXT_CHARS]
        truncated = True

    resolved_voice, voice_source = _resolve_voice(speaker, voice, cfg)
    if not resolved_voice:
        default_profile = _engine_config(cfg, "voicestudio").get("default_profile")
        if default_profile:
            resolved_voice = str(default_profile)
            voice_source = "default_profile"

    plan = _select_engines(requested_engine, cfg)
    if not plan:
        return {"ok": False, "engine": "", "path": None, "duration_sec": None,
                "sample_rate": None, "channels": None,
                "reason": "沒有任何可用的 TTS 引擎（請先跑 tts_doctor.py 排查）",
                "engine_payload": {"attempts": []}}

    attempts: List[Dict[str, Any]] = []
    last_reason = ""
    out_existed = out.exists()
    for engine_id in plan:
        synth = _ENGINE_SYNTH.get(engine_id)
        if synth is None:
            last_reason = f"未知引擎：{engine_id}"
            attempts.append({"engine": engine_id, "error": last_reason})
            continue
        engine_cfg = _engine_config(cfg, engine_id)
        try:
            payload = synth(clean, out, voice=resolved_voice, language=language,
                            engine_cfg=engine_cfg, extra=extra)
        except TtsError as exc:
            last_reason = redact_secrets(str(exc), _engine_secrets(engine_cfg))
            attempts.append({"engine": engine_id, "error": last_reason})
            if requested_engine != "auto":
                break
            continue
        except Exception as exc:                  # pragma: no cover - 防禦性攔截
            last_reason = redact_secrets(f"{type(exc).__name__}: {exc}", _engine_secrets(engine_cfg))
            attempts.append({"engine": engine_id, "error": last_reason})
            if requested_engine != "auto":
                break
            continue

        payload = dict(payload or {})
        payload["attempts"] = attempts
        payload["voice_resolved"] = resolved_voice
        payload["voice_source"] = voice_source
        payload["text_truncated"] = truncated
        info = _probe_audio(out)
        payload["audio"] = info
        return {
            "ok": True,
            "engine": engine_id,
            "path": str(out),
            "duration_sec": info.get("duration_sec"),
            "sample_rate": info.get("sample_rate"),
            "channels": info.get("channels"),
            "reason": "",
            "engine_payload": payload,
        }

    # 失敗時不要留下半成品，避免呼叫端誤把殘留檔當成成功輸出。
    if not out_existed:
        out.unlink(missing_ok=True)
    return {"ok": False, "engine": plan[-1] if plan else "", "path": None,
            "duration_sec": None, "sample_rate": None, "channels": None,
            "reason": last_reason or "所有 TTS 引擎都失敗",
            "engine_payload": {"attempts": attempts, "voice_resolved": resolved_voice,
                               "voice_source": voice_source, "text_truncated": truncated}}


def list_voices(engine: str = "voicestudio", config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """列出可用的音色；只有 voicestudio 可列出，fish / openai_compat 不可探索故回 []。"""
    cfg = config if isinstance(config, dict) else load_config()
    engine_id = str(engine or "voicestudio").strip().lower()
    if engine_id != "voicestudio":
        return []
    engine_cfg = _engine_config(cfg, engine_id)
    profiles = _vs_fetch_profiles(engine_cfg)

    voices: List[Dict[str, Any]] = []
    for profile in profiles:
        voices.append({
            "id": str(profile.get("id") or ""),
            "name": str(profile.get("name") or ""),
            "description": str(profile.get("description") or ""),
            "language": str(profile.get("language") or ""),
            "voice_type": str(profile.get("voice_type") or ""),
            "preset_engine": str(profile.get("preset_engine") or ""),
            "preset_voice_id": str(profile.get("preset_voice_id") or ""),
            "default_engine": str(profile.get("default_engine") or ""),
            "personality": bool(profile.get("personality")),
            "source": "profile",
        })

    # 預設音色（preset voices）：依設定與 profile 上出現過的引擎去抓一次。
    engines: List[str] = []
    configured = str(engine_cfg.get("default_voice_engine") or "").strip()
    if configured:
        engines.append(configured)
    for profile in profiles:
        preset_engine = str(profile.get("preset_engine") or "").strip()
        if preset_engine and preset_engine not in engines:
            engines.append(preset_engine)
    for preset_engine in engines:
        try:
            response = _http_request("GET", f"{_vs_base_url(engine_cfg)}/profiles/presets/{preset_engine}",
                                     timeout=10.0)
            if response.status >= 400:
                continue
            payload = response.json()
        except Exception:
            continue
        for item in _iter_preset_items(payload):
            voices.append({
                "id": str(item.get("id") or item.get("voice_id") or item.get("name") or ""),
                "name": str(item.get("name") or item.get("label") or item.get("voice_id") or ""),
                "description": str(item.get("description") or ""),
                "language": str(item.get("language") or ""),
                "voice_type": "preset",
                "preset_engine": preset_engine,
                "preset_voice_id": str(item.get("id") or item.get("voice_id") or ""),
                "default_engine": preset_engine,
                "personality": False,
                "source": "preset",
            })
    return voices


def _iter_preset_items(payload: Any) -> List[Dict[str, Any]]:
    """把 /profiles/presets/{engine} 的回應（結構未在 spec 明定）轉成字典清單。"""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("presets", "voices", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        # {name: {...}} 形式
        collected: List[Dict[str, Any]] = []
        for key, value in payload.items():
            if isinstance(value, dict):
                entry = dict(value)
                entry.setdefault("id", key)
                entry.setdefault("name", key)
                collected.append(entry)
        if collected:
            return collected
    return []


# ==============================================================================
# CLI（薄包裝，主要介面在 tts_doctor.py）
# ==============================================================================

def main() -> int:
    """命令列入口：--doctor 盤點環境、--list-voices 列出音色。"""
    import argparse

    parser = argparse.ArgumentParser(description="tts_engine.py — 可插拔 TTS 後端封裝")
    parser.add_argument("--doctor", action="store_true", help="列出各 TTS 引擎可用性")
    parser.add_argument("--list-voices", action="store_true", help="列出可探索的音色")
    parser.add_argument("--engine", type=str, default="voicestudio", help="--list-voices 要查詢的引擎")
    args = parser.parse_args()

    if args.doctor:
        try:
            from tts_doctor import collect_report, print_human
        except ImportError:                          # pragma: no cover - 路徑 fallback
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from tts_doctor import collect_report, print_human
        print_human(collect_report())
        return 0

    if args.list_voices:
        for voice in list_voices(args.engine):
            print(f"- {voice.get('name')}  [{voice.get('source')}] id={voice.get('id')}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
