import os
import sys
from typing import Optional

# 允许直接通过 `python app/main.py` 运行：将项目根目录加入 sys.path
if __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv

from app.agents.browser_use_runner import (
    is_available as browser_use_available,
    run_task_with_browser_use_async,
)
from app.schemas import RunCaseRequest, RunCaseResponse
from app.report import write_simple_report


app = FastAPI(title="UI 自动化 · 最小服务", version="0.3.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/run-case", response_model=RunCaseResponse)
async def run_case(req: RunCaseRequest) -> RunCaseResponse:
    if not req.task:
        raise HTTPException(status_code=400, detail="缺少 task")
    if not browser_use_available():
        raise HTTPException(status_code=400, detail="未安装 browser-use，请先 pip install browser-use")

    try:
        result_json = await run_task_with_browser_use_async(
            task=req.task,
            model=req.model,
            headless=bool(req.headless),
            success_criteria=[c.model_dump() for c in (req.success_criteria or [])],
            metadata=req.metadata,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"browser-use 执行失败：{e}")

    def _derive_ok(res: dict) -> bool:
        # 1) 明确布尔字段
        for key in ("ok", "success", "passed"):
            if key in res:
                val = res.get(key)
                if isinstance(val, bool):
                    return val
                sval = str(val).lower()
                if sval in ("true", "1", "yes"):
                    return True
                if sval in ("false", "0", "no"):
                    return False
        # 2) status 字段
        status = str(res.get("status", "")).lower()
        if status in ("ok", "success", "passed", "pass", "done", "completed"):
            return True
        if status in ("fail", "failed", "error", "exception"):
            return False
        # 3) 错误集合
        if res.get("error") or res.get("exception") or res.get("traceback"):
            return False
        if isinstance(res.get("errors"), (list, tuple)) and len(res.get("errors")) > 0:
            return False
        if isinstance(res.get("failures"), (list, tuple)) and len(res.get("failures")) > 0:
            return False
        # 4) 无法判定时，默认失败，避免误判成功
        return False

    ok = _derive_ok(result_json if isinstance(result_json, dict) else {})
    report_path = write_simple_report(
        task=req.task,
        success_criteria=req.success_criteria,
        ok=ok,
        raw=result_json,
    )
    return RunCaseResponse(
        ok=ok,
        message="执行完成" if ok else "执行失败",
        report_path=report_path,
        raw=result_json,
    )


def main() -> None:
    load_dotenv()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    use_reload = os.getenv("USE_UVICORN_RELOAD", "false").lower() == "true"
    if use_reload:
        uvicorn.run("app.main:app", host=host, port=port, reload=True)
    else:
        uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()


