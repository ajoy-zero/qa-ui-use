import os
from typing import Optional, Any, Dict

import httpx
import asyncio

from browser_use.llm.openai.chat import ChatOpenAI


def is_available() -> bool:
    try:
        import browser_use  # noqa: F401
        return True
    except Exception:
        return False

prompt = """
You are a testing agent that validates whether an application works as expected.

You'll be given a task description, steps, and success criteria. You need to

1. Follow the steps in order exactly as they are given.
2. Fill in the missing steps if needed but not deviate from the original steps.
3. Evaluate whether you can perform all steps in the exact order they are given.
4. Evaluate the end state of the application against the success criteria.
5. Only evaluate the end state once all previous steps have successfully been performed.

# Running the Test

- Perform the steps in the exact order they are given.
- Do not search for potential fixes or workarounds.
- Keep explicit track (e.g. in a list) of the steps you have performed in your actions.

# Success and Failure Criteria for Steps

- If you cannot perform a step, the test is failing.
- If you can perform a step, but the next step is not possible, the test is failing.
- If you need to retry a step, the test is failing unless explicitly stated otherwise in the step.
- If you can perform all steps, but the end state does not match exactly the success criteria, the test is failing.

# Success and Failure Criteria for the Evaluation

You need to evaluate whether all requirements for the evaluation are met. Anything beyond the evaluation is not considered.

For example:

- If the screen needs to show a button with explicit text "Search", but the button is not visible, or shows "Find", the test is failing.
- If the screen needs to show at least one result, but no results are visible, the test is failing.
- If the screen needs to show no results and there's one, the test is failing.
- If the screen needs to show at least five results, but only shows four, the test is failing.
- If the screen needs to show a specific error message, but shows a different one, the test is failing.

# Response Format

Return a JSON object with the following format:

{ ...RESPONSE_JSON_SCHEMA 内容，此处省略... }Return `{ status: "pass", steps: undefined, error: undefined }` if you can successfully perform the task.

Return `{ status: "failing", steps: [ { id: <number>, description: "<action that was taken>" } ], error: "<error message>" }` if you cannot successfully perform the test. The steps array contains exactly the steps that were successfully performed and nothing more. If you cannot perform a step, the error message contains information about why the step failed and reference the step label. If the final state does not match the success criteria, the error message is a detailed short description explaining what is different on the actual application compared to the expected application state and success criteria.

Additionally:

- DO NOT INCLUDE ANY OTHER TEXT IN YOUR RESPONSE.
- CORRECTLY CHOOSE THE ID FOR EACH STEP.
- STEPS NEED TO BE RETURNED IN THE EXACT ORDER THEY WERE GIVEN.
- STRICTLY FOLLOW THE RESPONSE FORMAT DEFINED ABOVE!

# Prompt Format

You'll be given 
1. a high level description of a task you are validating (e.g. "validate that the user can create a new search"), 
2. a list of steps you need to take to get there,
3. a success criteria for the final state of the application (e.g. "the app is on the search results page and is showing results").

The task will be given in the following format:

"""

def http_available() -> bool:
    """
    当设置了 BROWSER_USE_HTTP_BASE 环境变量时，走本地 browser-use HTTP 服务模式。
    例如：export BROWSER_USE_HTTP_BASE=http://127.0.0.1:7788
    可选：export BROWSER_USE_HTTP_RUN_PATH=/api/agent/run
    """
    return bool(os.getenv("BROWSER_USE_HTTP_BASE"))


def run_task_with_browser_use_http(
    task: str,
    model: Optional[str],
    headless: bool,
    success_criteria: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    通过本地 browser-use 的 HTTP API 执行任务。
    - BROWSER_USE_HTTP_BASE: 例如 http://127.0.0.1:7788
    - BROWSER_USE_HTTP_RUN_PATH: 例如 /api/agent/run （按你的服务实际调整）

    请求体示例（可根据你的 HTTP 服务契约调整）：
    {
      "task": "...",
      "model": "qwen2.5:7b",
      "headless": false,
      "success_criteria": [...],   # 可放在 extra.success_criteria
      "options": {...}             # 其他可选参数
    }
    """
    base = os.getenv("BROWSER_USE_HTTP_BASE")
    if not base:
        raise RuntimeError("缺少 BROWSER_USE_HTTP_BASE 环境变量。")
    run_path = os.getenv("BROWSER_USE_HTTP_RUN_PATH", "/run")
    url = f"{base.rstrip('/')}{run_path}"

    model_name = model or os.getenv("LLM_MODEL")
    payload: Dict[str, Any] = {
        "task": task,
        "model": model_name,
        "headless": headless,
    }
    if success_criteria is not None:
        payload["success_criteria"] = success_criteria
    if metadata is not None:
        payload["metadata"] = metadata

    timeout_s = float(os.getenv("BROWSER_USE_HTTP_TIMEOUT", "120"))
    headers: Dict[str, str] = {}
    auth_header_val = os.getenv("BROWSER_USE_HTTP_AUTH_HEADER")
    if auth_header_val:
        # 默认使用 Authorization 头；如需自定义头名，可后续扩展
        headers["Authorization"] = auth_header_val

    with httpx.Client(timeout=timeout_s, headers=headers or None) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        # 返回服务的原始 JSON，便于平台展示与后续对齐
        return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"text": resp.text}


def run_task_with_browser_use(
    task: str,
    model: Optional[str] = None,
    headless: bool = True,
    success_criteria: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    本地包模式：直接调用 browser-use 在本机控制浏览器。
    尽量兼容不同版本的 browser-use，如存在 BrowserSession 则优先使用 CDP 连接。
    """
    try:
        # 根据不同版本的导出，尽量兼容
        try:
            from browser_use import Agent  # type: ignore
        except Exception as e:
            raise RuntimeError("未找到 browser_use.Agent，请确认已安装并版本兼容。") from e
        try:
            from browser_use import BrowserSession  # type: ignore
        except Exception:
            BrowserSession = None  # type: ignore
        try:
            from browser_use import Browser  # type: ignore
        except Exception:
            Browser = None  # type: ignore
    except Exception as e:
        raise RuntimeError("未安装 browser-use，请先安装后再使用该功能。") from e

    model_name = model or os.getenv("LLM_MODEL")

    # 构造更稳定的提示词：系统规则 + 严格 JSON Schema + 任务与成功标准
    def build_prompt(base_task: str, succ: Optional[Any]) -> str:
        rules = (
            "你是一名严格的 UI 自动化测试代理。\n"
            "目标：1) 根据“任务（task）”在真实浏览器中稳定执行操作；"
            "2) 根据“成功标准（success_criteria）”判定结果；"
            "3) 只输出严格 JSON，满足下述 schema，不要任何多余文本。\n\n"
            "稳定性规则（必须遵守）：\n"
            "- 交互前确保元素可见且可点击；必要时滚动/等待网络空闲/等待过渡动画结束。\n"
            "- 定位优先级：可见文本/语义 > role/aria/data-testid > 稳定 text/placeholder/label > CSS/XPath（尽量避免）。\n"
            "- 尝试至多 2 次恢复（关闭弹窗、展开折叠、轻度滚动）；仍失败则停止并输出失败原因。\n"
            "- 不要输出推理过程或链路思考；不要返回除 JSON 之外内容。\n"
            "- 所有断言必须产出布尔结果与原因说明。\n\n"
            "输出 JSON Schema（严格遵守键名与类型）：\n"
            "{\n"
            '  "ok": boolean,\n'
            '  "status": "success" | "failed",\n'
            '  "title": string,\n'
            '  "url": string,\n'
            '  "asserts": [\n'
            "    {\n"
            '      "name": string,\n'
            '      "passed": boolean,\n'
            '      "actual": string,\n'
            '      "expected": string,\n'
            '      "why_failed": string\n'
            "    }\n"
            "  ],\n"
            '  "artifacts": { "screenshots": [string] },\n'
            '  "errors": [string]\n'
            "}\n\n"
        )
        succ_lines: list[str] = []
        if succ:
            try:
                for c in succ:
                    ctype = c.get("type")
                    selector = c.get("selector")
                    val = c.get("value")
                    if selector:
                        succ_lines.append(f"- {ctype}: [{selector}] {val}")
                    else:
                        succ_lines.append(f"- {ctype}: {val}")
            except Exception:
                pass
        succ_block = "\n".join(succ_lines) if succ_lines else "(无)"
        final_text = (
            rules
            + "任务（task）：\n"
            + base_task
            + "\n\n成功标准（success_criteria）：\n"
            + succ_block
            + "\n\n仅输出上述 JSON，不要任何其他文本。\n"
        )
        return final_text
    composed_task = build_prompt(task, success_criteria)

    # 优先尝试通过 CDP 连接本地浏览器
    cdp_url = os.getenv("BROWSER_USE_CDP_URL")
    agent = None
    try:
        if BrowserSession and cdp_url:
            session = BrowserSession(cdp_url=cdp_url)  # type: ignore
            agent = Agent(task=composed_task, browser_session=session, model=model_name)  # type: ignore
        elif Browser:
            # 一些版本可能允许直接传 browser/配置，若不支持则回退仅传 task
            try:
                browser = Browser(headless=headless)  # type: ignore
                agent = Agent(task=composed_task, browser=browser, model=model_name)  # type: ignore
            except Exception:
                agent = Agent(task=composed_task, model=model_name)  # type: ignore
        else:
            agent = Agent(task=composed_task, model=model_name)  # type: ignore
    except Exception as e:
        # 完全回退：最小参数构造
        agent = Agent(task=composed_task)  # type: ignore

    # 一些版本可能支持 metadata/context，尝试附加
    if agent is not None and metadata:
        try:
            setattr(agent, "metadata", metadata)  # type: ignore[attr-defined]
        except Exception:
            pass

    try:
        result = agent.run()  # type: ignore
    except Exception as e:
        raise RuntimeError(f"browser-use 本地执行失败：{e}")

    # 尝试标准化返回
    if isinstance(result, dict):
        return result  # 包含步骤/截图/状态等
    try:
        return {"text": str(result)}
    except Exception:
        return {"ok": True}


async def run_task_with_browser_use_async(
    task: str,
    model: Optional[str] = None,
    headless: bool = True,
    success_criteria: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    官方文档风格：
        llm = ChatBrowserUse()
        agent = Agent(task=..., llm=llm)
        await agent.run()
    """
    try:
        # Agent
        try:
            from browser_use import Agent  # type: ignore
        except Exception as e:
            raise RuntimeError("未找到 browser_use.Agent，请确认已安装并版本兼容。") from e

        # ChatBrowserUse 位置可能不同版本不同，做两种尝试
        try:
            from browser_use import ChatBrowserUse  # type: ignore
        except Exception:
            try:
                from browser_use.llm import ChatBrowserUse  # type: ignore
            except Exception as e2:
                raise RuntimeError("未找到 ChatBrowserUse，请确认 browser-use 版本与文档一致。") from e2
    except Exception as e:
        raise RuntimeError("未安装或无法导入 browser-use，请先 `pip install browser-use`。") from e

    def build_prompt(base_task: str, succ: Optional[Any]) -> str:
        rules = (
            "你是一名严格的 UI 自动化测试代理。\n"
            "目标：1) 根据“任务（task）”在真实浏览器中稳定执行操作；"
            "2) 根据“成功标准（success_criteria）”判定结果；"
            "3) 只输出严格 JSON，满足下述 schema，不要任何多余文本。\n\n"
            "稳定性规则（必须遵守）：\n"
            "- 交互前确保元素可见且可点击；必要时滚动/等待网络空闲/等待过渡动画结束。\n"
            "- 定位优先级：可见文本/语义 > role/aria/data-testid > 稳定 text/placeholder/label > CSS/XPath（尽量避免）。\n"
            "- 尝试至多 2 次恢复（关闭弹窗、展开折叠、轻度滚动）；仍失败则停止并输出失败原因。\n"
            "- 不要输出推理过程或链路思考；不要返回除 JSON 之外内容。\n"
            "- 所有断言必须产出布尔结果与原因说明。\n\n"
            "输出 JSON Schema（严格遵守键名与类型）：\n"
            "{\n"
            '  "ok": boolean,\n'
            '  "status": "success" | "failed",\n'
            '  "title": string,\n'
            '  "url": string,\n'
            '  "asserts": [\n'
            "    {\n"
            '      "name": string,\n'
            '      "passed": boolean,\n'
            '      "actual": string,\n'
            '      "expected": string,\n'
            '      "why_failed": string\n'
            "    }\n"
            "  ],\n"
            '  "artifacts": { "screenshots": [string] },\n'
            '  "errors": [string]\n'
            "}\n\n"
        )
        succ_lines: list[str] = []
        if succ:
            try:
                for c in succ:
                    ctype = c.get("type")
                    selector = c.get("selector")
                    val = c.get("value")
                    succ_lines.append(f"- {ctype}: {('['+selector+'] ') if selector else ''}{val}")
            except Exception:
                pass
        succ_block = "\n".join(succ_lines) if succ_lines else "(无)"
        final_text = (
            rules
            + "任务（task）：\n"
            + base_task
            + "\n\n成功标准（success_criteria）：\n"
            + succ_block
            + "\n\n仅输出上述 JSON，不要任何其他文本。\n"
        )
        return final_text
    composed_task = build_prompt(task, success_criteria)
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key = os.getenv('ALIBABA_CLOUD')

    # 构造 LLM：有的版本支持传 model，有的版本不支持，做兼容尝试
    llm = ChatOpenAI(model='qwen-vl-plus', api_key=api_key, base_url=base_url)

    # 构造 Agent：官方示例只传 task 与 llm
    agent = Agent(
        task=composed_task,
        llm=llm,
        use_vision=True,
    )  # type: ignore
    if metadata:
        try:
            setattr(agent, "metadata", metadata)  # type: ignore[attr-defined]
        except Exception:
            pass

    try:
        result = await agent.run()  # type: ignore
    except Exception as e:
        raise RuntimeError(f"browser-use 异步执行失败：{e}")

    if isinstance(result, dict):
        return result
    try:
        return {"text": str(result)}
    except Exception:
        return {"ok": True}


