"""四步会计核算流水线的共享状态。所有步骤都写入同一份 State，保证可追溯和可断点续跑。"""
from __future__ import annotations
from typing import Any, TypedDict
from pydantic import BaseModel, Field, field_validator

STEP1 = "step1_classification"
STEP2 = "step2_vouchers"
STEP3 = "step3_statements"
STEP4 = "step4_comparison"
STEPS = (STEP1, STEP2, STEP3, STEP4)

class AIReviewNote(BaseModel):
    """模型语义复核的固定返回结构，避免把 Markdown 或自由文本直接写入状态。"""
    summary: str = ""
    anomalies: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def coerce_summary(cls, value: Any) -> str:
        return value if isinstance(value, str) else str(value or "")

    @field_validator("anomalies", "recommendations", mode="before")
    @classmethod
    def coerce_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        return [item if isinstance(item, str) else str(item) for item in value]

class InvoiceClassificationItem(BaseModel):
    # 字段顺序就是前端 JSON 和表格的观察顺序。
    invoice_id: str
    source_file: str
    ocr_text: str = ""
    label: str
    matched_rule: str = ""
    confidence: float = Field(ge=0, le=1)
    invoice_number: str = ""
    invoice_date: str = ""
    seller: str = ""
    buyer: str = ""
    description: str = ""
    line_count: int = 0
    amount: float = 0.0
    tax_amount: float = 0.0
    total_amount: float = 0.0
    invoice_direction: str = "unknown"
    recommended_debit_account: str = ""
    recommended_credit_account: str = ""

class ClassificationOutput(BaseModel):
    invoices: list[InvoiceClassificationItem]
    rules_reference: str = ""
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    dataset_status: str
    model_note: AIReviewNote | None = None
    table_csv: dict[str, str] = Field(default_factory=dict)
    table_files: list[dict[str, Any]] = Field(default_factory=list)
    table_preview: list[dict[str, Any]] = Field(default_factory=list)

class VouchersOutput(BaseModel):
    vouchers: list[dict[str, Any]]
    bank_source: str = ""
    bank_excerpt: str = ""
    bank_transactions: list[dict[str, Any]] = Field(default_factory=list)
    unmatched_invoices: list[dict[str, Any]] = Field(default_factory=list)
    unmatched_transactions: list[dict[str, Any]] = Field(default_factory=list)
    balanced: bool
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    dataset_status: str
    model_note: AIReviewNote | None = None
    table_csv: dict[str, str] = Field(default_factory=dict)
    table_files: list[dict[str, Any]] = Field(default_factory=list)
    table_preview: list[dict[str, Any]] = Field(default_factory=list)

class StatementsOutput(BaseModel):
    trial_balance: dict[str, Any]
    balance_sheet: dict[str, Any]
    income_statement: dict[str, Any]
    cash_flow_statement: dict[str, Any]
    adjustments: list[dict[str, Any]] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    dataset_status: str
    model_note: AIReviewNote | None = None
    # 三张报表先以稳定的 CSV 文本进入 State，再由 API 物化为 xlsx。
    report_csv: dict[str, str] = Field(default_factory=dict)
    report_files: list[dict[str, Any]] = Field(default_factory=list)
    table_csv: dict[str, str] = Field(default_factory=dict)
    table_files: list[dict[str, Any]] = Field(default_factory=list)
    table_preview: list[dict[str, Any]] = Field(default_factory=list)

class ComparisonOutput(BaseModel):
    current_metrics: dict[str, Any]
    historical_sources: list[dict[str, Any]] = Field(default_factory=list)
    comparisons: list[dict[str, Any]]
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    report: str = ""
    dataset_status: str
    model_note: AIReviewNote | None = None

OUTPUT_MODELS = {
    STEP1: ClassificationOutput,
    STEP2: VouchersOutput,
    STEP3: StatementsOutput,
    STEP4: ComparisonOutput,
}

class AccountingState(TypedDict, total=False):
    workflow_id: str
    thread_id: str
    tenant_id: str
    user_id: str
    invoice_paths: list[str]
    rules_path: str
    bank_path: str
    history_paths: list[str]
    use_llm: bool
    current_step: str
    retry_step: str
    status: str
    step_outputs: dict[str, dict[str, Any]]
    confidence: float
    risk: float
    review_context: dict[str, Any]
    pending_action: dict[str, Any]
    audit_log: list[dict[str, Any]]
    checkpoint_version: int
    error: str
