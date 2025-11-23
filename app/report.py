import json
import pathlib
import time
import shutil
import base64
from typing import Any, Dict, List, Optional

import httpx

from app.schemas import SuccessCriterion


ARTIFACTS_DIR = pathlib.Path("artifacts")
REPORTS_DIR = ARTIFACTS_DIR / "reports"
SCREENSHOTS_DIR = ARTIFACTS_DIR / "screenshots"


def _ensure_dirs() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def _save_png_bytes(png_bytes: bytes, idx: int) -> str:
    ts = int(time.time() * 1000)
    path = SCREENSHOTS_DIR / f"snap-{ts}-{idx}.png"
    path.write_bytes(png_bytes)
    return str(path)


def _try_base64_to_bytes(s: str) -> Optional[bytes]:
    try:
        # data URL
        if s.startswith("data:image"):
            comma = s.find(",")
            if comma != -1:
                s = s[comma + 1 :]
        # base64 decode
        return base64.b64decode(s, validate=False)
    except Exception:
        return None


def persist_screenshots_into_artifacts(raw: Dict[str, Any]) -> List[str]:
    """
    将 raw.artifacts.screenshots 中的条目统一落盘到 artifacts/screenshots：
    - data URL/base64: 解码为 PNG
    - 本地路径: 复制
    - 远程 URL: 下载为 PNG
    返回保存后的相对路径列表，并回写 raw.artifacts.screenshots
    """
    _ensure_dirs()
    artifacts = raw.get("artifacts") or {}
    shots = artifacts.get("screenshots") or []
    if not isinstance(shots, list) or not shots:
        return []

    saved_paths: List[str] = []
    for i, item in enumerate(shots):
        try:
            # 统一成字符串
            s = item if isinstance(item, str) else str(item)
            s = s.strip()
            # base64/data URL
            b = _try_base64_to_bytes(s)
            if b:
                saved_paths.append(_save_png_bytes(b, i))
                continue
            # 本地文件
            p = pathlib.Path(s)
            if p.exists() and p.is_file():
                ts = int(time.time() * 1000)
                dst = SCREENSHOTS_DIR / f"snap-{ts}-{i}{p.suffix or '.png'}"
                shutil.copyfile(str(p), str(dst))
                saved_paths.append(str(dst))
                continue
            # 远程 URL
            if s.startswith("http://") or s.startswith("https://"):
                with httpx.Client(timeout=30) as client:
                    r = client.get(s)
                    r.raise_for_status()
                    saved_paths.append(_save_png_bytes(r.content, i))
                continue
        except Exception:
            # 跳过异常项，不中断整体
            continue
    # 回写
    artifacts["screenshots"] = saved_paths
    raw["artifacts"] = artifacts
    return saved_paths


def write_simple_report(
    task: str,
    success_criteria: Optional[List[SuccessCriterion]],
    ok: bool,
    raw: Dict[str, Any],
) -> str:
    _ensure_dirs()
    # 默认将截图统一落盘，并将路径回写到 raw.artifacts.screenshots
    try:
        persist_screenshots_into_artifacts(raw)
    except Exception:
        # 忽略截图落盘失败，仍生成报告
        pass
    ts = int(time.time() * 1000)
    report_path = REPORTS_DIR / f"report-{ts}.html"
    criteria_html = ""
    if success_criteria:
        items = "".join(
            f"<li><b>{c.type}</b> {f'[{c.selector}] ' if c.selector else ''}{c.value}</li>"
            for c in success_criteria
        )
        criteria_html = f"<ul>{items}</ul>"
    raw_pretty = json.dumps(raw, ensure_ascii=False, indent=2)
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>用例报告 - {ts}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 24px; }}
    .ok {{ color: #0a7f2e; }}
    .fail {{ color: #b00020; }}
    pre {{ background: #f6f8fa; padding: 12px; border-radius: 6px; overflow: auto; }}
    code {{ white-space: pre-wrap; word-break: break-word; }}
  </style>
  </head>
<body>
  <h2>用例报告</h2>
  <p><b>任务</b>：{task}</p>
  <p><b>结果</b>：<span class="{ 'ok' if ok else 'fail' }">{ '成功' if ok else '失败' }</span></p>
  <h3>成功标准</h3>
  {criteria_html or '<p>（未提供）</p>'}
  <h3>原始返回</h3>
  <pre><code>{raw_pretty}</code></pre>
</body>
</html>"""
    report_path.write_text(html, encoding="utf-8")
    return str(report_path)



