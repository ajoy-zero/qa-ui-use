# 最小可运行示例：FastAPI + browser-use（HTTP，本地浏览器）

本项目提供：

- FastAPI 接口：接收自然语言任务，通过本地 browser-use 的 HTTP 服务驱动本地浏览器执行
- 可选回退：若未配置 HTTP，也可调用本地 `browser-use` Python 包（如已安装）

## 1. 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

可选安装 browser-use（仅在未配置 HTTP 服务时用于本地包回退）：
```bash
pip install browser-use
```

使用 browser-use 本地 HTTP 服务：
- 请启动你已有的 browser-use HTTP 服务，并记录其地址与运行路径
- 设置环境变量：
```bash
export BROWSER_USE_HTTP_BASE="http://127.0.0.1:7788"
export BROWSER_USE_HTTP_RUN_PATH="/run"   # 按你的服务实际调整，默认 /run
```

控制是否有头运行（默认无头）：
```bash
export HEADLESS=true  # 或 false
```

## 2. 启动 FastAPI

```bash
uvicorn app.main:app --reload --port 8000
```

或从 main 方法启动（会自动读取 .env）：
```bash
python -m app.main
# 或
python app/main.py
```

### 2.1 使用 browser-use 本地 HTTP（由 browser-use 执行本地浏览器）

```bash
curl -X POST http://localhost:8000/run-case \
  -H 'Content-Type: application/json' \
  -d '{
    "provider": "browser-use",
    "model": "qwen2.5:7b",               // 可选：透传给 browser-use 服务
    "headless": false,
    "task": "打开 https://example.com 并验证标题包含 Example Domain",
    "extra": {
      "success_criteria": [
        {"type": "title_contains", "value": "Example Domain"}
      ],
      "options": {
        "max_steps": 8
      }
    }
  }'
```

> 说明：需先设置 `BROWSER_USE_HTTP_BASE`（与可选 `BROWSER_USE_HTTP_RUN_PATH`）。服务端返回原始 JSON 将放入 `artifacts.browser_use_response`。

## 3. 平台化考虑（建议）

- API 设计：`/run-case` 接收 `task` + `provider=browser-use`，可携带 `extra.success_criteria`
- 可扩展：对齐你的 browser-use HTTP 契约，透传更多 `options`
- 产物：可由 browser-use 服务返回截图/轨迹；本服务原样返回 JSON（artifacts.browser_use_response）
- 安全：接口鉴权（生产）、最小权限环境变量管理

## .env 示例（自行在项目根目录创建 .env）
```
# 本地 browser-use HTTP 服务
BROWSER_USE_HTTP_BASE=http://127.0.0.1:7788
BROWSER_USE_HTTP_RUN_PATH=/run
# 若你的服务需要认证头，配置如下（示例：Bearer XXX）
BROWSER_USE_HTTP_AUTH_HEADER=
# HTTP 超时（秒）
BROWSER_USE_HTTP_TIMEOUT=120

# 大模型默认（若请求未显式传 model，则使用该值）
LLM_MODEL=qwen2.5:7b

# 服务参数
HOST=127.0.0.1
PORT=8000
USE_UVICORN_RELOAD=false

# 运行模式（供业务侧参考）
HEADLESS=false
```

提示：你也可以直接修改项目根目录的 `env.example` 后复制为 `.env` 使用。

## 4. API 请求结构说明

- 接口
  - 方法：POST
  - 路径：/run-case
  - 头：Content-Type: application/json

- 请求体字段
  - task (string, 必填)：自然语言描述要执行的业务目标/步骤（尽量简洁）
  - success_criteria (array<object>, 可选)：任务级断言（针对整个 task，而非逐步）
    - type (string)：目前支持 title_contains | text_exists | url_contains
    - value (string)：期望文本或片段
    - selector (string, 可选)：可省略，默认走语义定位
  - headless (boolean, 默认 true)：是否无头
  - model (string, 可选)：大模型名（不传则使用 .env 的 LLM_MODEL）
  - metadata (object, 可选)：自定义元信息（如 caseId）

- 说明
  - success_criteria 为“任务级断言”，用于对整个 task 结束后的状态做判断；不是逐步断言
  - 如需逐步判断，建议将大流程拆成多个短 task 依次调用，或扩展协议为 steps 形式

- 响应体字段
  - ok (boolean)：是否成功
  - message (string)：执行结果文案
  - report_path (string)：HTML 报告路径（artifacts/reports/）
  - raw (object)：browser-use 执行原始返回（结构化 JSON）

- 示例（校验 GitHub 首页标题包含“GitHub”）
```bash
curl -X POST http://localhost:8000/run-case \
  -H 'Content-Type: application/json' \
  -d '{
    "task": "打开 https://github.com 并等待页面加载完成，用于后续校验。",
    "success_criteria": [
      {"type": "title_contains", "value": "GitHub"}
    ],
    "headless": false,
    "model": "qwen-vl-plus",
    "metadata": {"caseId": "github-title-001"}
  }'
```


