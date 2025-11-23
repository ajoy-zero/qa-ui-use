from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field


class SuccessCriterion(BaseModel):
    type: Literal["title_contains", "text_exists", "url_contains"]
    selector: Optional[str] = Field(default=None, description="仅当 type=text_exists 时可选")
    value: str


class RunCaseRequest(BaseModel):
    task: str = Field(description="自然语言描述的测试目标（browser-use 将据此执行）")
    success_criteria: Optional[List[SuccessCriterion]] = Field(
        default=None, description="可选的结构化成功标准，将透传给 browser-use 服务"
    )
    headless: bool = Field(default=True, description="是否无头运行（最终由 browser-use 决定）")
    model: Optional[str] = Field(default=None, description="模型名（可选，透传给 browser-use）")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="可选，透传的元信息")


class RunCaseResponse(BaseModel):
    ok: bool
    message: str
    report_path: str
    raw: Dict[str, Any] = Field(default_factory=dict)


