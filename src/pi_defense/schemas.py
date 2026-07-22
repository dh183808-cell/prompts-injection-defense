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
    action: Literal["allow_original", "repair", "conservative_block"]
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
    base_case_id: str
    architecture: Literal["B0", "B1", "B2", "B3"]
    kind: Literal["benign", "direct", "indirect"]
    attack_family: Optional[str] = None
    configured_model: str
    actual_model: Optional[str] = None
    target_output: str
    leaked: bool
    leak_variant: Optional[str] = None
    task_correct_auto: Optional[bool] = None
    task_correct_manual: Optional[bool] = None
    failure_category: Optional[Literal["over_refusal", "task_hijacked", "incorrect", "none"]] = None
    over_refusal: bool = False
    task_hijacked: bool = False
    task_correct: Optional[bool] = None
    latency_ms: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None

    # Phase B — metadata
    system_prompt_mode: Optional[Literal["minimal", "hardened"]] = None
    system_prompt_hash: Optional[str] = None
    dataset_seed: Optional[int] = None
    dataset_hash: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 256
    git_commit: Optional[str] = None

    # B1 — defender
    defender_is_attack: bool = False
    defender_repaired: bool = False
    defender_model: Optional[str] = None
    defender_latency_ms: Optional[float] = None
    defender_input_tokens: Optional[int] = None
    defender_output_tokens: Optional[int] = None
    defender_raw: Optional[str] = None

    # B2 — detectors + OR + repair
    detector_0_suspicious: Optional[bool] = None
    detector_1_suspicious: Optional[bool] = None
    detector_2_suspicious: Optional[bool] = None
    detector_0_latency_ms: Optional[float] = None
    detector_1_latency_ms: Optional[float] = None
    detector_2_latency_ms: Optional[float] = None
    detector_0_model: Optional[str] = None
    detector_1_model: Optional[str] = None
    detector_2_model: Optional[str] = None
    or_triggered: bool = False
    repair_action: Optional[str] = None
    repair_latency_ms: Optional[float] = None
    repair_model: Optional[str] = None
    repair_raw: Optional[str] = None

    # B3 — adjudicator
    adjudicator_confirmed: bool = False
    adjudicator_action: Optional[str] = None
    adjudicator_latency_ms: Optional[float] = None
    adjudicator_model: Optional[str] = None
    adjudicator_raw: Optional[str] = None

    error: Optional[str] = None
    timestamp: str = ""

    def model_post_init(self, __context):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.run_id:
            self.run_id = f"b0_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"