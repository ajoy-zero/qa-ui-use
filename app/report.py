import json
import pathlib
import time
from typing import Any, Dict, List, Optional

from app.schemas import SuccessCriterion


ARTIFACTS_DIR = pathlib.Path("artifacts")
REPORTS_DIR = ARTIFACTS_DIR / "reports"


def _ensure_dirs() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def write_simple_report(
    task: str,
    success_criteria: Optional[List[SuccessCriterion]],
    ok: bool,
    raw: Dict[str, Any],
) -> str:
    _ensure_dirs()
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



