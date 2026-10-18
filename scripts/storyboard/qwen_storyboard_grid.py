#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen-Image 2.1 Turbo 電影分鏡九宮格草圖生成、局部重繪與自動拼版工具
(Qwen Storyboard Grid Generator & Assembler v1.0)

功能：
1. 本機 FreeVideo 連線與安全握手（嚴格保護 Token 不外洩）。
2. 分鏡轉黑白鉛筆手繪草圖 Prompt 編譯器（含透視線、動態黑箭頭與排線光影）。
3. 嚴格 1:1 映射逐格生成（panel-{index:02d}-{shot_id}.png）與單格局部重繪（--redraw-shot）。
4. 審核保護機制：審核通過（approved/locked）的格子自動跳過，防止重抽污染。
5. 自動拼合 3x3 九宮格分鏡總覽圖（grid-{segment_id}.png），帶鏡頭規格資訊條與回寫 Layer 2 JSON。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

# 確保 Windows 終端以 UTF-8 輸出，避免繁體中文字元編碼異常
if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ==============================================================================
# 安全與連線模組 (FreeVideo Client)
# ==============================================================================

class FreeVideoClient:
    """管理本機 FreeVideo 連線與生圖 API，嚴格遵守安全規範，絕不輸出 Token。"""

    def __init__(self, base_url: str = "http://127.0.0.1:8189"):
        self.base_url = base_url.rstrip("/")
        self._token: Optional[str] = None

    def locate_and_load_token(self) -> str:
        """動態自接入說明解析或本機目錄讀取令牌，存於記憶體，絕不印出或寫入檔案。"""
        if self._token:
            return self._token

        # 1. 嘗試從 /connect?lang=zh 文字說明解析 token 檔案路徑
        connect_url = f"{self.base_url}/freevideo/agent/v1/connect?lang=zh"
        found_paths: List[pathlib.Path] = []
        try:
            req = urllib.request.Request(connect_url, headers={"User-Agent": "FreeVideoClient/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
                for line in text.splitlines():
                    # 匹配類似 E:\FreeVideo\agent\token 或路徑特徵
                    match = re.search(r"([A-Za-z]:\\[^:\*\?\"<>\|]+\\token|~[/\\]\.freevideo[/\\]token)", line)
                    if match:
                        raw_p = match.group(1).replace("/", "\\")
                        p = pathlib.Path(os.path.expanduser(raw_p))
                        if p.exists() and p not in found_paths:
                            found_paths.append(p)
        except Exception:
            pass

        # 2. 備用候選路徑
        default_candidates = [
            pathlib.Path("E:/FreeVideo/agent/token"),
            pathlib.Path.home() / ".freevideo" / "token",
            pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "FreeVideo" / "token",
        ]
        for c in default_candidates:
            if c.exists() and c not in found_paths:
                found_paths.append(c)

        for token_file in found_paths:
            try:
                content = token_file.read_text(encoding="utf-8").strip()
                if content:
                    self._token = content
                    return self._token
            except Exception:
                continue

        raise RuntimeError(
            "無法取得 FreeVideo 令牌（Token）。請確認本機 FreeVideo 正在運行，"
            "且 E:\\FreeVideo\\agent\\token 或 ~/.freevideo/token 檔案存在。"
        )

    def _get_headers(self) -> Dict[str, str]:
        token = self.locate_and_load_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "QwenStoryboardGrid/1.0",
        }

    def verify_connection(self) -> Dict[str, Any]:
        """驗證連線、執行握手並檢查佇列狀態。看到任何原有未完成任務絕不改動。"""
        # 1. 檢查 agent 狀態
        agent_url = f"{self.base_url}/freevideo/agent"
        try:
            with urllib.request.urlopen(agent_url, timeout=5) as r:
                data = json.loads(r.read().decode("utf-8"))
                if not data.get("enabled", False):
                    raise RuntimeError("FreeVideo Agent API 未啟用 (enabled: false)")
        except urllib.error.URLError as e:
            raise RuntimeError(f"無法連線至 FreeVideo 服務 ({self.base_url}): {e}")

        # 2. 握手 /connect/hello
        hello_url = f"{self.base_url}/freevideo/agent/v1/connect/hello"
        hello_payload = json.dumps({"client": "qwen_storyboard_grid", "via": "http"}).encode("utf-8")
        req = urllib.request.Request(hello_url, data=hello_payload, headers=self._get_headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                _ = r.read()
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"FreeVideo 握手失敗 (HTTP {e.code}): {err_body}")

        # 3. 查詢根資訊與佇列狀態
        root_url = f"{self.base_url}/freevideo/agent/v1"
        req = urllib.request.Request(root_url, headers=self._get_headers(), method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            root_info = json.loads(r.read().decode("utf-8"))

        if not root_info.get("ready", False):
            raise RuntimeError(f"FreeVideo 引擎尚未就緒: problem={root_info.get('problem')}")

        return root_info

    def upload_media(self, file_path: pathlib.Path) -> str:
        """上傳本機圖片至 FreeVideo 媒體庫，回傳供生成任務引用的檔案路徑識別碼。"""
        import base64
        if not file_path.exists():
            raise FileNotFoundError(f"找不到要上傳的媒體檔案: {file_path}")

        media_url = f"{self.base_url}/freevideo/agent/v1/media"
        b64_data = base64.b64encode(file_path.read_bytes()).decode("ascii")
        payload = {
            "name": file_path.name,
            "data_base64": b64_data,
        }
        req = urllib.request.Request(
            media_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._get_headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"上傳媒體至 FreeVideo 失敗 (HTTP {e.code}): {err_msg}")

        file_id = data.get("file")
        if not file_id:
            raise RuntimeError(f"上傳媒體未取得 file 欄位，伺服器回傳: {data}")
        return file_id

    def submit_image_job(
        self,
        prompt: str,
        aspect: str = "16:9",
        label: str = "分鏡鉛筆草圖",
        seed: Optional[int] = None,
        images: Optional[List[str]] = None,
    ) -> str:
        """提交 Qwen-Image 2.1 生圖任務至佇列。"""
        jobs_url = f"{self.base_url}/freevideo/agent/v1/jobs"
        payload: Dict[str, Any] = {
            "kind": "image",
            "prompt": prompt,
            "aspect": aspect,
            "label": label[:120],
        }
        if seed is not None:
            payload["seed"] = int(seed)
        if images:
            payload["images"] = images

        req = urllib.request.Request(
            jobs_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._get_headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"提交生圖任務失敗 (HTTP {e.code}): {err_msg}")

        job_info = data.get("job") or (data.get("jobs", [{}])[0] if data.get("jobs") else {})
        job_id = job_info.get("id")
        if not job_id:
            raise RuntimeError(f"未取得任務 ID，伺服器回傳: {data}")
        return job_id

    def poll_job_until_done(
        self,
        job_id: str,
        wait_seconds: int = 25,
        timeout_seconds: int = 240,
    ) -> Dict[str, Any]:
        """長輪詢任務直到成功或失敗。"""
        t0 = time.time()
        while True:
            if time.time() - t0 > timeout_seconds:
                raise TimeoutError(f"任務 {job_id} 生成逾時 ({timeout_seconds}s)")

            poll_url = f"{self.base_url}/freevideo/agent/v1/jobs/{job_id}?wait={wait_seconds}"
            req = urllib.request.Request(poll_url, headers=self._get_headers(), method="GET")
            try:
                with urllib.request.urlopen(req, timeout=wait_seconds + 5) as r:
                    job = json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                err_msg = e.read().decode("utf-8", errors="ignore")
                raise RuntimeError(f"輪詢任務 {job_id} 失敗 (HTTP {e.code}): {err_msg}")

            status = job.get("status")
            if status == "succeeded":
                return job.get("result", {})
            elif status in ("failed", "cancelled", "interrupted"):
                err_detail = job.get("error", {}) or job.get("problem", "未知錯誤")
                raise RuntimeError(f"任務 {job_id} 終止，狀態為 {status}，詳情: {err_detail}")

            time.sleep(1)

    def download_image(self, file_url_or_path: str, destination_path: pathlib.Path) -> bytes:
        """從 FreeVideo 下載生成產物並寫入本機路徑。"""
        if file_url_or_path.startswith("http://") or file_url_or_path.startswith("https://"):
            full_url = file_url_or_path
        else:
            clean_path = file_url_or_path.lstrip("/")
            full_url = f"{self.base_url}/{clean_path}"

        req = urllib.request.Request(full_url, headers=self._get_headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"下載圖片失敗 (HTTP {e.code}): {err_msg}")

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_bytes(data)
        return data


# ==============================================================================
# Prompt 編譯器 (分鏡轉黑白鉛筆草圖)
# ==============================================================================

def build_pencil_sketch_prompt(
    shot: Dict[str, Any],
    segment_data: Optional[Dict[str, Any]] = None,
    no_arrows: bool = False,
) -> str:
    """針對 Qwen-Image 2.1 Turbo (CFG=1.0，無負向詞，英文第三人稱現在式客觀描述)

    編譯電影黑白石墨鉛筆手繪草圖提示詞，強調：
    1. 人物走位與姿態 (Character placement & pose)
    2. 場景透視結構線與滅點 (Architectural perspective construction lines & vanishing points)
    3. 景別與焦距透視 (Shot size, focal length perspective & depth of field)
    4. 動作方向與運鏡黑箭頭 (Bold black hand-drawn directional arrows) 或純淨底稿 (no_arrows)
    5. 純灰階石墨排線光影、乾淨線條、無對話氣泡、無字體浮水印。
    """
    cam = shot.get("camera_optics", {})
    blocking = shot.get("spatial_blocking", {})
    action = shot.get("action_and_performance", {})

    shot_size = cam.get("shot_size", "MS")
    focal = cam.get("focal_length", "35mm")
    movement = cam.get("movement", "Static")
    pov = cam.get("pov_routing", "objective")
    distance = cam.get("physical_distance", "medium distance")

    blocking_desc = blocking.get("blocking_desc", "")
    anchors = blocking.get("anchor_objects", [])
    anchor_str = ", ".join(anchors) if anchors else "architectural environment"

    action_stages = action.get("action_stages", [])
    action_str = "; ".join(action_stages) if action_stages else "character holding pose"
    expression = action.get("observable_expression", "focused and composed expression")

    # 1. 鏡頭焦段透視感轉譯
    lens_perspective_map = {
        "14mm": "14mm ultra-wide perspective, strong peripheral barrel expansion and dramatic depth stretch",
        "24mm": "24mm wide angle perspective, exaggerated near-to-far spatial scaling and rapid linear convergence",
        "35mm": "35mm natural environmental wide perspective, balanced human-to-space spatial relationship",
        "50mm": "50mm true-to-life standard prime perspective, zero geometric distortion, human eye natural depth",
        "85mm": "85mm portrait telephoto compression, shallow depth of field isolating subject from soft blurred background",
        "100mm": "100mm telephoto telephoto compression, background heavily flattened and stacked against subject profile",
        "135mm": "135mm extreme telephoto compression, razor-thin focal plane and monumental background stacking",
    }
    lens_desc = lens_perspective_map.get(focal, f"{focal} cinematic lens perspective")

    # 2. 景別轉譯
    shot_size_map = {
        "ELS": "Extreme Long Shot (ELS), environmental scale establishing shot",
        "LS": "Long Shot (LS), full character bodies integrated in spacious environment",
        "MLS": "Medium Long Shot (MLS), characters framed from knees up",
        "MS": "Medium Shot (MS), character framed from waist up in spatial context",
        "MCU": "Medium Close-Up (MCU), character framed from chest up with clear facial performance",
        "CU": "Close-Up (CU), tight framing emphasizing facial features and intense gaze",
        "ECU": "Extreme Close-Up (ECU), macro detail framing on specific gesture, weapon edge, or eyes",
        "OTS_MS": "Over-The-Shoulder Medium Shot (OTS), foreground shoulder framing the opposite speaker",
        "OTS_CU": "Over-The-Shoulder Close-Up (OTS), tight focus past blurred foreground figure",
    }
    framing_desc = shot_size_map.get(shot_size, f"{shot_size} cinematic framing")

    # 3. 視角與走位遮擋規則
    pov_desc_map = {
        "objective": "Third-person objective camera perspective adhering strictly to 180-degree axis line",
        "dirty_frame_20_35": "Voyeuristic dirty-frame composition, partially occluded by blurred architectural foreground element on one side",
        "clear_impact_90deg": "Perpendicular 90-degree profile side view, unobstructed line of action exposing exact contact point and force trajectory",
        "defensive_reaction_ots": "Defensive OTS angle past foreground shoulder, focusing sharply on listener's three-quarter facial reaction",
        "reflection_delay": "Composition framing reflected image in mirror or water surface before shifting attention to subject",
    }
    pov_desc = pov_desc_map.get(pov, "cinematic perspective")

    # 4. 判斷是否生成方向指示箭頭
    if no_arrows:
        directional_line = "Directional annotation: Clean composition layout without any hand-drawn arrows, motion indicators, or construction annotations."
    else:
        directional_line = "Directional annotation: Bold black hand-drawn directional arrows indicating subject motion, action trajectory, and camera movement."

    # 5. 組裝結構化 Prompt
    parts = [
        "A monochrome graphite pencil storyboard sketch on off-white paper, cinematic blocking and composition diagram.",
        f"Cinematic framing: {framing_desc}, {lens_desc}, camera distance: {distance}.",
        f"Camera angle & blocking: {pov_desc}. Camera movement: {movement}.",
        f"Spatial environment & perspective: Architectural perspective construction lines and visible vanishing point guidelines showing {anchor_str}. Spatial layout: {blocking_desc}.",
        f"Character action & pose: {action_str}. Character expression: {expression}.",
        directional_line,
        "Artistic technique: Pure grayscale pencil cross-hatching, hatching line shading, rough animatic concept art, crisp hand-drawn sketch lines, no speech bubbles, no colored elements, no text overlays, no watermarks.",
    ]

    return " ".join(parts)


STYLE_CONSISTENCY_WARNING = (
    "[⚠️ 畫風一致性警告（噩盡島第五輪實測教訓）] "
    "外部生圖模型生成的彩色首幀畫風 ≠ H3 原生 Ref2VA 畫風。"
    "若本片採用「每段獨立 Ref2VA」為主力，請勿將單段首幀 I2VA 混入片中（畫風會跳出來）；"
    "若要使用首幀 I2VA，請務必與既有 H3 片段並排對照畫風，或整部片統一皆由同一圖片模型生成首幀。"
)


def build_color_keyframe_prompt(shot: Dict[str, Any], segment_data: Optional[Dict[str, Any]] = None) -> str:
    """編譯黑白鉛筆分鏡草圖轉全彩關鍵幀首幀提示詞，強制注入屬性解耦擦除指令。

    將單格鉛筆草圖作為 <image1> 送入 FreeVideo Qwen-Image 2.1 Turbo，
    嚴格保留構圖幾何與人體姿態，同時完全去除方向箭頭與輔助線，轉為真實色彩與光影。
    """
    print(STYLE_CONSISTENCY_WARNING)
    segment_data = segment_data or {}
    meta = segment_data.get("metadata", {})
    style_anchor = (
        shot.get("style_lock")
        or segment_data.get("style_lock")
        or meta.get("style_lock")
        or "Cinematic photorealistic 3D, dramatic lighting, high fidelity, 8k resolution"
    )

    base_directive = (
        f"Convert the monochrome pencil storyboard sketch in <image1> into a full-color cinematic keyframe "
        f"following the style lock ({style_anchor}). "
        f"Strictly preserve the exact camera framing, perspective geometry, and character pose from <image1>, "
        f"but completely remove all black hand-drawn directional arrows, motion indicator lines, "
        f"and perspective construction grid lines, replacing them with natural scene surfaces and lighting."
    )

    # 提取角色、走位、光影等自然細節作為輔助描述
    blocking = shot.get("spatial_blocking", {})
    action = shot.get("action_and_performance", {})
    cam = shot.get("camera_optics", {})

    details = []
    if blocking.get("blocking_desc"):
        details.append(f"Scene environment: {blocking['blocking_desc']}")
    if action.get("observable_expression"):
        details.append(f"Subject expression and appearance: {action['observable_expression']}")
    if action.get("action_stages"):
        details.append(f"Action context: {'; '.join(action['action_stages'])}")
    if shot.get("lighting"):
        details.append(f"Lighting atmosphere: {shot['lighting']}")
    if cam.get("shot_size"):
        details.append(f"Framing: {cam.get('shot_size')}")

    if details:
        return f"{base_directive} Detailed scene elements: {'; '.join(details)}."
    return base_directive


# ==============================================================================
# 單格生成與局部重繪
# ==============================================================================

def compute_file_sha256(path: pathlib.Path) -> str:
    """計算檔案的 SHA256 雜湊值。"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def process_storyboard_segment(
    client: FreeVideoClient,
    layer2_data: Dict[str, Any],
    out_dir: pathlib.Path,
    generate_all: bool = False,
    redraw_shot_id: Optional[str] = None,
    no_arrows: bool = False,
    seed: Optional[int] = None,
    dry_run: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """逐格生成或局部重繪。

    回傳：(更新後的 layer2_data, {shot_id: file_sha256})
    """
    shots = layer2_data.get("shots", [])
    if not shots:
        raise ValueError("Layer 2 JSON 中未包含任何 shots 鏡頭資料！")

    panels_dir = out_dir / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)

    sha256_map: Dict[str, str] = {}
    total_shots = len(shots)

    print(f"\n[開始分鏡處理] 專案: {layer2_data.get('project_id')} | 場次: {layer2_data.get('scene_id')} | 段落: {layer2_data.get('segment_id')}")
    print(f"總鏡頭數: {total_shots} 鏡 | 目標輸出目錄: {panels_dir}")

    for idx, shot in enumerate(shots, start=1):
        shot_id = shot.get("shot_id", f"SH{idx:02d}")
        panel_filename = f"panel-{idx:02d}-{shot_id}.png"
        panel_path = panels_dir / panel_filename

        # 判斷是否需要生成此格
        should_generate = False
        skip_reason = ""

        review_info = shot.get("review", {})
        is_locked = review_info.get("locked", False)
        review_status = review_info.get("review_status", "draft")

        if redraw_shot_id:
            if shot_id == redraw_shot_id:
                should_generate = True
                print(f"\n-> [#格號 {idx:02d}] 命中重繪目標鏡頭 {shot_id}！強制重新生圖。")
            else:
                should_generate = False
                skip_reason = "非重繪指定鏡頭（局部重繪保護其餘格完全不觸碰）"
        elif generate_all:
            if panel_path.exists() and (is_locked or review_status == "approved"):
                should_generate = False
                skip_reason = f"已審核通過且鎖定 ({review_status}, locked={is_locked})，自動跳過防止重抽"
            else:
                should_generate = True
        else:
            # 未指定 generate_all 也未指定 redraw_shot_id，僅做檢查
            should_generate = False
            skip_reason = "未指定 --generate-all 或 --redraw-shot"

        # 編譯提示詞
        prompt = build_pencil_sketch_prompt(shot, layer2_data, no_arrows=no_arrows)
        shot["sketch_prompt"] = prompt

        if not should_generate:
            if panel_path.exists():
                h = compute_file_sha256(panel_path)
                sha256_map[shot_id] = h
                shot["sketch_file"] = str(panel_path.relative_to(out_dir).as_posix())
                shot["sketch_sha256"] = h
                print(f"  [#格號 {idx:02d}] {shot_id}: 跳過生成 ({skip_reason}) | 現有圖 SHA256: {h[:12]}...")
            else:
                print(f"  [#格號 {idx:02d}] {shot_id}: 圖片不存在且未觸發生圖 ({skip_reason})")
            continue

        print(f"\n-> [#格號 {idx:02d}] 正在為鏡頭 {shot_id} 生成黑白鉛筆分鏡草圖...")
        print(f"   景別焦段: {shot.get('camera_optics', {}).get('shot_size')} {shot.get('camera_optics', {}).get('focal_length')} | 時長: {shot.get('duration')}s")
        print(f"   Prompt 長度: {len(prompt)} 字元")

        if dry_run:
            print("   [DRY RUN] 略過實際呼叫 FreeVideo API。")
            continue

        # 呼叫 FreeVideo 生圖
        t_start = time.time()
        job_id = client.submit_image_job(
            prompt=prompt,
            aspect="16:9",
            label=f"分鏡草圖-{idx:02d}-{shot_id}",
            seed=seed,
        )
        print(f"   任務已提交，ID: {job_id}，正在長輪詢等待 Qwen-Image 2.1 渲染...")

        try:
            result = client.poll_job_until_done(job_id=job_id, wait_seconds=25, timeout_seconds=240)
        except Exception as e:
            if "no_memory" in str(e).lower():
                print(f"\n❌ [FreeVideo 顯存不足錯誤 (no_memory)]: {e}")
                check_gpu_vram(verbose=True)
            raise

        dur = time.time() - t_start

        # 下載圖片至指定單格路徑
        download_url = result.get("url") or result.get("thumbnail")
        if not download_url:
            raise RuntimeError(f"生圖結果中未包含下載 URL: {result}")

        client.download_image(download_url, panel_path)
        h = compute_file_sha256(panel_path)
        sha256_map[shot_id] = h

        # 更新 Layer 2 結構
        shot["sketch_file"] = str(panel_path.relative_to(out_dir).as_posix())
        shot["sketch_sha256"] = h
        shot["sketch_status"] = "generated"
        shot["status"] = "image_done"
        if "review" not in shot:
            shot["review"] = {}
        shot["review"]["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        print(f"   [成功完成] 耗時: {dur:.1f}s | 儲存至: {panel_path.name} | SHA256: {h[:12]}...")

    return layer2_data, sha256_map


def convert_to_color_keyframes(
    client: FreeVideoClient,
    layer2_data: Dict[str, Any],
    out_dir: pathlib.Path,
    target_shot: str,
    seed: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """將已核准的單格鉛筆草圖轉繪為全彩關鍵幀首幀，自動注入屬性解耦擦除指令。"""
    shots = layer2_data.get("shots", [])
    if not shots:
        raise ValueError("Layer 2 JSON 中未包含任何 shots 鏡頭資料！")

    keyframes_dir = out_dir / "keyframes"
    keyframes_dir.mkdir(parents=True, exist_ok=True)
    panels_dir = out_dir / "panels"

    print(f"\n[開始轉繪全彩關鍵幀首幀] 目標: {target_shot} | 目標輸出目錄: {keyframes_dir}")

    for idx, shot in enumerate(shots, start=1):
        shot_id = shot.get("shot_id", f"SH{idx:02d}")
        if target_shot != "all" and shot_id != target_shot:
            continue

        # 尋找單格鉛筆草圖檔案
        sketch_rel = shot.get("sketch_file")
        sketch_path: Optional[pathlib.Path] = None
        if sketch_rel:
            p = out_dir / sketch_rel
            if p.exists():
                sketch_path = p
        if not sketch_path:
            candidate = panels_dir / f"panel-{idx:02d}-{shot_id}.png"
            if candidate.exists():
                sketch_path = candidate

        keyframe_filename = f"keyframe-{shot_id}.png"
        keyframe_path = keyframes_dir / keyframe_filename

        # 編譯全彩關鍵幀提示詞
        color_prompt = build_color_keyframe_prompt(shot, layer2_data)
        shot["color_keyframe_prompt"] = color_prompt

        print(f"\n-> [#格號 {idx:02d}] 正在為鏡頭 {shot_id} 轉繪全彩關鍵幀首幀...")
        print(f"   Prompt 長度: {len(color_prompt)} 字元")

        if dry_run:
            print("   [DRY RUN] 略過實際呼叫 FreeVideo API，模擬更新 Layer 2 資料。")
            shot["image_file"] = str(keyframe_path.relative_to(out_dir).as_posix())
            shot["keyframe_file"] = str(keyframe_path.relative_to(out_dir).as_posix())
            shot["keyframe_status"] = "dry_run"
            shot["status"] = "image_done"
            if "review" not in shot:
                shot["review"] = {}
            shot["review"]["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            continue

        if not sketch_path or not sketch_path.exists():
            print(f"   [警告] 找不到鏡頭 {shot_id} 的鉛筆草圖檔案，無法作為參考圖轉彩，略過此鏡頭。")
            continue

        # 1. 上傳草圖至 FreeVideo 媒體庫
        print(f"   正在上傳參考鉛筆草圖: {sketch_path.name} ...")
        t_start = time.time()
        media_file_id = client.upload_media(sketch_path)
        shot["sketch_media_file"] = media_file_id

        # 2. 提交轉彩生圖任務
        job_id = client.submit_image_job(
            prompt=color_prompt,
            aspect="16:9",
            label=f"全彩關鍵幀-{idx:02d}-{shot_id}",
            seed=seed,
            images=[media_file_id],
        )
        print(f"   轉彩任務已提交，ID: {job_id}，正在長輪詢等待 Qwen-Image 2.1 渲染...")

        result = client.poll_job_until_done(job_id=job_id, wait_seconds=25, timeout_seconds=240)
        dur = time.time() - t_start

        # 下載圖片至指定關鍵幀路徑
        download_url = result.get("url") or result.get("thumbnail")
        if not download_url:
            raise RuntimeError(f"轉彩生圖結果中未包含下載 URL: {result}")

        client.download_image(download_url, keyframe_path)
        h = compute_file_sha256(keyframe_path)

        # 更新 Layer 2 結構
        shot["image_file"] = str(keyframe_path.relative_to(out_dir).as_posix())
        shot["keyframe_file"] = str(keyframe_path.relative_to(out_dir).as_posix())
        shot["keyframe_sha256"] = h
        shot["keyframe_status"] = "generated"
        shot["status"] = "image_done"
        if "review" not in shot:
            shot["review"] = {}
        shot["review"]["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        print(f"   [成功完成] 耗時: {dur:.1f}s | 儲存至: {keyframe_path.name} | SHA256: {h[:12]}...")

    return layer2_data


# ==============================================================================
# GPU 顯存 4.20 GiB 檢測與友善診斷模組
# ==============================================================================

def check_gpu_vram(threshold_mb: int = 4300, verbose: bool = True) -> Dict[str, Any]:
    """檢測 GPU 可用顯存，針對 FreeVideo 4.20 GiB (4300 MiB) 硬門檻提供友善診斷。"""
    import subprocess
    info = {
        "available": False,
        "free_mb": 0,
        "used_mb": 0,
        "total_mb": 0,
        "threshold_mb": threshold_mb,
        "is_safe": False,
        "diff_mb": 0,
        "top_processes": [],
    }
    try:
        cmd = ["nvidia-smi", "--query-gpu=memory.free,memory.used,memory.total", "--format=csv,noheader,nounits"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        parts = [int(x.strip()) for x in res.stdout.strip().split(",")]
        info["free_mb"], info["used_mb"], info["total_mb"] = parts[0], parts[1], parts[2]
        info["available"] = True
        info["is_safe"] = info["free_mb"] >= threshold_mb
        info["diff_mb"] = max(0, threshold_mb - info["free_mb"])

        # 查詢吃顯存的程序
        pcmd = ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"]
        pres = subprocess.run(pcmd, capture_output=True, text=True)
        if pres.stdout.strip():
            for line in pres.stdout.strip().splitlines()[:10]:
                if line.strip():
                    info["top_processes"].append(line.strip())
    except Exception as e:
        if verbose:
            print(f"[顯存檢測提示] 無法透過 nvidia-smi 獲取顯存資訊: {e}")
        return info

    if verbose:
        print("\n" + "=" * 80)
        print(f"📊 [GPU 顯存診斷] 總量: {info['total_mb']} MiB | 已用: {info['used_mb']} MiB | 可用: {info['free_mb']} MiB")
        print(f"   FreeVideo Qwen-Image 2.1 引擎硬性安全門檻: {threshold_mb} MiB (4.20 GiB)")
        if not info["is_safe"]:
            print(f"⚠️ 【顯存不足警告】距離 4.20 GiB 門檻尚差 {info['diff_mb']} MiB！生圖任務可能觸發 no_memory 中斷！")
            if info["top_processes"]:
                print("   當前佔用 GPU 之進程清單:")
                for p in info["top_processes"]:
                    print(f"     - {p}")
            print("   👉 排除指引: 請關閉高顯存消耗的背景程式（如瀏覽器硬體加速、動態桌布、大型應用）以釋放約 300~500 MB 顯存。")
        else:
            print(f"✅ GPU 可用顯存充足（高於 {threshold_mb} MiB），可安全執行生圖。")
        print("=" * 80 + "\n")

    return info


# ==============================================================================
# 自適應分鏡拼版模組 (Compact, 3x3, Episode-Pages, Segment-Rep)
# ==============================================================================

def get_preferred_font(size: int = 18) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """嘗試載入中文字型，找不到時退回預設字型。"""
    font_candidates = [
        "C:/Windows/Fonts/msyh.ttc",    # 微軟雅黑
        "C:/Windows/Fonts/simhei.ttf",  # 黑體
        "C:/Windows/Fonts/arial.ttf",   # Arial
        "C:/Windows/Fonts/segoeui.ttf", # Segoe UI
    ]
    for fp in font_candidates:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_grid_canvas(
    shots: List[Dict[str, Any]],
    cols: int,
    rows: int,
    header_title: str,
    header_subtitle: str,
    out_dir: pathlib.Path,
    save_path: pathlib.Path,
) -> pathlib.Path:
    """底層通用拼版渲染器：依據指定 cols x rows 拼合畫布，徹底避免多餘空白格。"""
    panel_w = 800
    panel_h = 450   # 16:9
    bar_h = 56      # 底部資訊條
    cell_w = panel_w
    cell_h = panel_h + bar_h

    margin = 24
    gap = 18
    header_h = 100

    total_w = margin * 2 + cell_w * cols + gap * (cols - 1)
    total_h = margin * 2 + header_h + cell_h * rows + gap * (rows - 1)

    bg_color = (20, 24, 33)
    grid_img = Image.new("RGB", (total_w, total_h), bg_color)
    draw = ImageDraw.Draw(grid_img)

    font_title = get_preferred_font(28)
    font_meta = get_preferred_font(18)
    font_bar = get_preferred_font(17)
    font_empty = get_preferred_font(32)

    # 1. 繪製頂部 Header
    hx0, hy0 = margin, margin
    hx1, hy1 = total_w - margin, margin + header_h
    draw.rectangle([hx0, hy0, hx1, hy1], fill=(13, 17, 23), outline=(48, 54, 61), width=2)
    draw.text((hx0 + 20, hy0 + 16), header_title, fill=(240, 246, 252), font=font_title)
    draw.text((hx0 + 20, hy0 + 58), header_subtitle, fill=(139, 148, 158), font=font_meta)

    # 2. 逐格排版
    panels_dir = out_dir / "panels"
    total_cells = cols * rows

    for grid_idx in range(total_cells):
        col = grid_idx % cols
        row = grid_idx // cols
        x = margin + col * (cell_w + gap)
        y = margin + header_h + gap + row * (cell_h + gap)

        if grid_idx < len(shots):
            shot = shots[grid_idx]
            shot_id = shot.get("shot_id", f"SH{grid_idx+1:02d}")
            panel_file = shot.get("sketch_file") or shot.get("image_file")
            panel_path: Optional[pathlib.Path] = None

            if panel_file:
                p = out_dir / panel_file
                if p.exists():
                    panel_path = p
                else:
                    cand = pathlib.Path(panel_file)
                    if cand.exists():
                        panel_path = cand

            if not panel_path:
                candidate = panels_dir / f"panel-{grid_idx+1:02d}-{shot_id}.png"
                if candidate.exists():
                    panel_path = candidate

            # 繪製單格草圖
            if panel_path and panel_path.exists():
                try:
                    with Image.open(panel_path) as p_img:
                        p_resized = p_img.convert("RGB").resize((panel_w, panel_h), Image.Resampling.LANCZOS)
                        grid_img.paste(p_resized, (x, y))
                except Exception as e:
                    draw.rectangle([x, y, x + panel_w, y + panel_h], fill=(40, 20, 20))
                    draw.text((x + 30, y + 200), f"讀取失敗: {e}", fill=(255, 100, 100), font=font_bar)
            else:
                draw.rectangle([x, y, x + panel_w, y + panel_h], fill=(30, 35, 45), outline=(55, 65, 81), width=1)
                draw.text((x + panel_w // 2 - 120, y + panel_h // 2 - 15), "[等待生成草圖]", fill=(120, 130, 150), font=font_empty)

            draw.rectangle([x, y, x + panel_w, y + panel_h], outline=(55, 65, 81), width=1)

            # 底部資訊條
            bar_y = y + panel_h
            draw.rectangle([x, bar_y, x + panel_w, bar_y + bar_h], fill=(13, 17, 23), outline=(55, 65, 81), width=1)

            cam = shot.get("camera_optics", {})
            shot_size = cam.get("shot_size", "MS")
            focal = cam.get("focal_length", "35mm")
            dur = shot.get("duration", 0.0)
            movement = cam.get("movement", "Static")
            review = shot.get("review", {})
            status = review.get("review_status", "draft")
            locked = review.get("locked", False)

            if locked or status == "approved":
                status_str, status_color = "APPROVED", (63, 185, 80)
            elif status == "rejected":
                status_str, status_color = "REJECTED", (248, 81, 73)
            else:
                status_str, status_color = "DRAFT", (88, 166, 255)

            line1 = f"[#{grid_idx+1:02d}] {shot_id}  |  {shot_size} {focal}  |  {dur:.1f}s  |  {movement}"
            draw.text((x + 12, bar_y + 8), line1, fill=(240, 246, 252), font=font_bar)
            draw.text((x + 12, bar_y + 30), f"審核: {status_str}", fill=status_color, font=font_bar)
            if review.get("reviewer_note"):
                draw.text((x + 140, bar_y + 30), f"備註: {review['reviewer_note'][:28]}", fill=(139, 148, 158), font=font_bar)

        else:
            # 空白格
            draw.rectangle([x, y, x + panel_w, y + panel_h], fill=(26, 30, 39), outline=(48, 54, 61), width=1)
            draw.text((x + panel_w // 2 - 200, y + panel_h // 2 - 16), f"[#{grid_idx+1:02d}] EMPTY PANEL", fill=(75, 85, 99), font=font_empty)
            bar_y = y + panel_h
            draw.rectangle([x, bar_y, x + panel_w, bar_y + bar_h], fill=(18, 21, 28), outline=(48, 54, 61), width=1)
            draw.text((x + 12, bar_y + 16), f"[#{grid_idx+1:02d}] (空鏡頭位)", fill=(100, 110, 125), font=font_bar)

    save_path.parent.mkdir(parents=True, exist_ok=True)
    grid_img.save(save_path, format="PNG", optimize=True)
    print(f"  [拼版產出] 已儲存至: {save_path.name} ({cols}x{rows} 格, 尺寸: {total_w}x{total_h})")
    return save_path


def assemble_adaptive_grid(
    layer2_data: Dict[str, Any],
    out_dir: pathlib.Path,
    grid_filename: Optional[str] = None,
    grid_mode: str = "auto",
) -> pathlib.Path:
    """單一 Layer 2 分段自適應拼版：消除單段 2~3 鏡印出 7 個 EMPTY PANEL 的問題。"""
    segment_id = layer2_data.get("segment_id", "S01")
    scene_id = layer2_data.get("scene_id", "SC01")
    project_id = layer2_data.get("project_id", "PROJ")
    shots = layer2_data.get("shots", [])
    n_shots = len(shots)

    if not grid_filename:
        grid_filename = f"grid-{segment_id}.png"
    save_path = out_dir / grid_filename

    # 計算行列
    if grid_mode == "3x3":
        cols, rows = 3, 3
    elif grid_mode == "compact" or (grid_mode == "auto" and n_shots <= 6):
        if n_shots <= 1:
            cols, rows = 1, 1
        elif n_shots == 2:
            cols, rows = 2, 1
        elif n_shots == 3:
            cols, rows = 3, 1
        elif n_shots == 4:
            cols, rows = 2, 2
        elif n_shots in (5, 6):
            cols, rows = 3, 2
        else:
            cols, rows = 3, 3
    else:
        cols, rows = 3, 3

    meta = layer2_data.get("metadata", {})
    dur = meta.get("target_duration_sec", sum(s.get("duration", 0) for s in shots))
    pacing = meta.get("pacing_profile", "Standard")
    now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    title = f"CINEMATIC STORYBOARD GRID ({cols}x{rows}) | {project_id} · {scene_id} · {segment_id}"
    subtitle = (
        f"鏡頭數: {n_shots} 鏡 ({cols}x{rows} 版面)  |  時長: {dur:.1f}s  |  節奏: {pacing}  |  "
        f"模型: Qwen-Image 2.1 (Pencil)  |  時間: {now_str}"
    )

    render_grid_canvas(
        shots=shots,
        cols=cols,
        rows=rows,
        header_title=title,
        header_subtitle=subtitle,
        out_dir=out_dir,
        save_path=save_path,
    )

    # 回寫 Layer 2 JSON
    layer2_data["grid_preview_file"] = str(save_path.relative_to(out_dir).as_posix())
    panel_manifest = []
    for idx, shot in enumerate(shots, start=1):
        panel_manifest.append({
            "index": idx,
            "shot_id": shot.get("shot_id"),
            "panel_file": shot.get("sketch_file") or shot.get("image_file"),
            "sha256": shot.get("sketch_sha256"),
        })
    layer2_data["storyboard_panels"] = panel_manifest
    return save_path


def assemble_episode_grids(
    segment_files: List[pathlib.Path],
    out_dir: pathlib.Path,
    episode_tag: str,
    grid_mode: str = "episode-pages",
) -> List[pathlib.Path]:
    """跨段整集拼版：支援每 9 鏡一頁滿版 3x3 (episode-pages) 或每段抽第 1 鏡 (segment-rep)。"""
    all_shots: List[Dict[str, Any]] = []
    rep_shots: List[Dict[str, Any]] = []

    for sf in segment_files:
        try:
            with sf.open("r", encoding="utf-8") as f:
                data = json.load(f)
            seg_shots = data.get("shots", [])
            all_shots.extend(seg_shots)
            if seg_shots:
                rep_shots.append(seg_shots[0])
        except Exception as e:
            print(f"[警告] 讀取分段檔案失敗 {sf.name}: {e}")

    output_paths: List[pathlib.Path] = []
    now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    if grid_mode == "segment-rep":
        # 抽取各段第 1 鏡組裝代表總覽圖 (取前 9 鏡)
        target_shots = rep_shots[:9]
        save_path = out_dir / f"grid-{episode_tag.lower()}-representative.png"
        title = f"CINEMATIC STORYBOARD REPRESENTATIVE 3x3 GRID | {episode_tag} (Segment Reps)"
        sub = f"總段落數: {len(segment_files)} 段  |  代表鏡數: {len(target_shots)}/9 鏡  |  時間: {now_str}"
        p = render_grid_canvas(
            shots=target_shots,
            cols=3,
            rows=3,
            header_title=title,
            header_subtitle=sub,
            out_dir=out_dir,
            save_path=save_path,
        )
        output_paths.append(p)

    else:
        # episode-pages：每 9 鏡切為一頁滿版 3x3
        total_shots = len(all_shots)
        pages = math.ceil(total_shots / 9) if total_shots > 0 else 1
        for page_idx in range(pages):
            page_shots = all_shots[page_idx * 9 : (page_idx + 1) * 9]
            save_path = out_dir / f"grid-{episode_tag.lower()}-p{page_idx+1}.png"
            title = f"CINEMATIC STORYBOARD 3x3 GRID | {episode_tag} · Page {page_idx+1}/{pages}"
            sub = f"整集鏡頭總數: {total_shots} 鏡 (本頁: {len(page_shots)} 鏡)  |  時間: {now_str}"
            p = render_grid_canvas(
                shots=page_shots,
                cols=3,
                rows=3,
                header_title=title,
                header_subtitle=sub,
                out_dir=out_dir,
                save_path=save_path,
            )
            output_paths.append(p)

    return output_paths


# ==============================================================================
# CLI 主程式
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Qwen-Image 2.1 Turbo 鉛筆分鏡自適應拼版與生圖工具 (升級版 v2.0)"
    )
    parser.add_argument("--layer2", type=str, default=None, help="單一 Layer 2 分鏡 JSON 檔案路徑")
    parser.add_argument("--layer2-dir", type=str, default=None, help="Layer 2 分段目錄 (批次處理整集多個 JSON)")
    parser.add_argument("--episode", type=str, default=None, help="指定集數過濾 (例如 EP01, EP02)")
    parser.add_argument("--out-dir", type=str, default=None, help="輸出圖片與九宮格目錄 (預設為 layer2 所在目錄)")
    parser.add_argument("--generate-all", action="store_true", help="逐格生成全部草圖 (自動跳過已鎖定/審核通過之單格)")
    parser.add_argument("--redraw-shot", type=str, default=None, help="指定單一 shot_id 進行局部重繪 (其餘格子完全不變)")
    parser.add_argument("--no-arrows", action="store_true", help="生成純淨無黑箭頭的鉛筆構圖底稿")
    parser.add_argument("--to-color-keyframe", type=str, default=None, metavar="SHOT_ID_OR_ALL", help="將指定 shot_id 或 'all' 轉繪為全彩首幀")
    parser.add_argument("--seed", type=int, default=None, help="生圖隨機種子")
    parser.add_argument("--assemble-grid", action="store_true", help="執行拼版總覽圖")
    parser.add_argument("--assemble-only", action="store_true", help="純拼版模式 (不呼叫生圖 API，適合離線排版驗收)")
    parser.add_argument("--grid-mode", type=str, default="auto", choices=["auto", "compact", "3x3", "episode-pages", "segment-rep"],
                        help="拼版模式: compact(自適應無空格), 3x3(固定九宮格), episode-pages(整集分頁九宮格), segment-rep(各段代表鏡總覽)")
    parser.add_argument("--grid-name", type=str, default=None, help="指定產出九宮格的檔案名稱")
    parser.add_argument("--check-vram", action="store_true", help="執行 GPU 顯存 4.20 GiB 檢測與診斷")
    parser.add_argument("--dry-run", action="store_true", help="只編譯提示詞並驗證連線，不實際調用生圖 API")

    args = parser.parse_args()

    # 1. 獨立顯存檢測
    if args.check_vram:
        check_gpu_vram(verbose=True)
        if not (args.layer2 or args.layer2_dir):
            sys.exit(0)

    # 2. 確定處理檔案列表
    layer2_files: List[pathlib.Path] = []
    if args.layer2:
        p = pathlib.Path(args.layer2).resolve()
        if not p.exists():
            print(f"[錯誤] 找不到檔案: {p}", file=sys.stderr)
            sys.exit(1)
        layer2_files.append(p)
    elif args.layer2_dir:
        dir_p = pathlib.Path(args.layer2_dir).resolve()
        if not dir_p.exists():
            print(f"[錯誤] 找不到目錄: {dir_p}", file=sys.stderr)
            sys.exit(1)
        pattern = f"*{args.episode}*.json" if args.episode else "*.json"
        layer2_files = sorted(dir_p.glob(pattern))
        if not layer2_files:
            print(f"[錯誤] 在 {dir_p} 找不到匹配 {pattern} 的分段 JSON 檔案！", file=sys.stderr)
            sys.exit(1)
    else:
        print("[錯誤] 請指定 --layer2 <檔案> 或 --layer2-dir <目錄>", file=sys.stderr)
        sys.exit(1)

    # 輸出目錄
    if args.out_dir:
        out_dir = pathlib.Path(args.out_dir).resolve()
    else:
        out_dir = layer2_files[0].parent
    out_dir.mkdir(parents=True, exist_ok=True)

    client = FreeVideoClient()

    # 3. 檢查連線 (若需要生圖)
    need_conn = (args.generate_all or args.redraw_shot or args.to_color_keyframe) and not args.assemble_only
    if need_conn:
        check_gpu_vram(verbose=True)
        print("[連線初始化] 正在檢查 FreeVideo 伺服器並握手...")
        try:
            root_info = client.verify_connection()
            queue_info = root_info.get("queue", {})
            print(f"  連線成功！FreeVideo 版本: {root_info.get('freevideo_version')} | 設備後端: {root_info.get('device', {}).get('backend')}")
            print(f"  佇列狀態: 執行中={queue_info.get('running')}, 佇列中={queue_info.get('pending')}")
        except Exception as e:
            if args.dry_run:
                print(f"  [DRY RUN 提示] FreeVideo 未連線 ({e})，仍可進行提示詞編譯測試。")
            else:
                print(f"[連線錯誤] {e}", file=sys.stderr)
                sys.exit(1)

    # 4. 逐檔處理生成
    for l2_path in layer2_files:
        with l2_path.open("r", encoding="utf-8") as f:
            l2_data = json.load(f)

        if (args.generate_all or args.redraw_shot or (args.dry_run and not args.to_color_keyframe)) and not args.assemble_only:
            l2_data, _ = process_storyboard_segment(
                client=client,
                layer2_data=l2_data,
                out_dir=out_dir,
                generate_all=args.generate_all,
                redraw_shot_id=args.redraw_shot,
                no_arrows=args.no_arrows,
                seed=args.seed,
                dry_run=args.dry_run,
            )
            with l2_path.open("w", encoding="utf-8") as f:
                json.dump(l2_data, f, ensure_ascii=False, indent=2)

        if args.to_color_keyframe and not args.assemble_only:
            print(f"\n{STYLE_CONSISTENCY_WARNING}\n")
            l2_data = convert_to_color_keyframes(
                client=client,
                layer2_data=l2_data,
                out_dir=out_dir,
                target_shot=args.to_color_keyframe,
                seed=args.seed,
                dry_run=args.dry_run,
            )
            with l2_path.open("w", encoding="utf-8") as f:
                json.dump(l2_data, f, ensure_ascii=False, indent=2)

        # 單檔自適應拼版
        if (args.assemble_grid or args.assemble_only) and args.grid_mode in ("auto", "compact", "3x3"):
            assemble_adaptive_grid(
                layer2_data=l2_data,
                out_dir=out_dir,
                grid_filename=args.grid_name,
                grid_mode=args.grid_mode,
            )
            with l2_path.open("w", encoding="utf-8") as f:
                json.dump(l2_data, f, ensure_ascii=False, indent=2)

    # 5. 跨段整集拼版 (episode-pages 或 segment-rep)
    if (args.assemble_grid or args.assemble_only) and args.grid_mode in ("episode-pages", "segment-rep"):
        ep_tag = args.episode or "ALL"
        print(f"\n[執行跨段整集拼版] 模式: {args.grid_mode} | 涵蓋分段數: {len(layer2_files)}")
        assemble_episode_grids(
            segment_files=layer2_files,
            out_dir=out_dir,
            episode_tag=ep_tag,
            grid_mode=args.grid_mode,
        )

    print("\n✅ [所有指定分鏡任務執行完畢]")


if __name__ == "__main__":
    main()

