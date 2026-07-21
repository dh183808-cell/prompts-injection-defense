import uuid
from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field


class ExperimentCase(BaseModel):
    case_id: str
    base_case_id: str

    kind: Literal["benign", "direct", "indirect"]
    task: str

    user_input: str
    external_content: str = ""

    expected_answer: Optional[str] = None

    attack_family: Optional[str] = None
    source_family: Optional[str] = None

    # 数据源元数据（9.1）
    source_type: Optional[Literal["copied", "adapted", "benchmark-inspired", "generated", "original"]] = None
    reference: Optional[str] = None
    adaptation_note: Optional[str] = None
    attack_transform: Optional[str] = None


class DetectorReport(BaseModel):
    suspicious: bool
    risk_score: float = Field(ge=0.0, le=1.0)

    attack_family: Optional[str] = None
    evidence_spans: list[str] = []

    protected_task: Optional[str] = None
    suspected_malicious_goal: Optional[str] = None

    reason: str


class AdjudicationReport(BaseModel):
    confirmed_attack: bool
    risk_score: float = Field(ge=0.0, le=1.0)

    final_category: Optional[str] = None
    evidence: list[str] = []

    action: Literal[
        "allow_original",
        "repair",
        "conservative_block",
    ]

    repair_strategy: Optional[str] = None
    reason: str


class RepairReport(BaseModel):
    repaired_prompt: str
    removed_content_summary: list[str] = []
    preserved_task_summary: str
    residual_risk: float = Field(ge=0.0, le=1.0)


class RunRecord(BaseModel):
    """单次实验运行的结果记录。"""

    run_id: str
    case_id: str
    base_case_id: str
    architecture: Literal["B0", "B1", "B2", "B3"]
    kind: Literal["benign", "direct", "indirect"]
    attack_family: Optional[str] = None

    configured_model: str
    actual_model: Optional[str] = None

    target_output: str

    leaked: bool
    leak_variant: Optional[str] = None

    task_correct: Optional[bool] = None

    latency_ms: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None

    error: Optional[str] = None
    timestamp: str = ""

    def model_post_init(self, __context):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.run_id:
            self.run_id = f"b0_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
