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
    run_id: str
    case_id: str
    architecture: Literal["B0", "B1", "B2", "B3"]

    configured_model: str
    actual_model: Optional[str] = None

    target_output: str

    leaked: bool
    leak_variant: Optional[str] = None

    task_correct: Optional[bool] = None

    latency_ms: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
