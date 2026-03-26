from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMBaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SourceConfigRead(ORMBaseModel):
    key: str
    name: str
    base_url: str
    collector_kind: str
    enabled: bool
    schedule_minutes: int
    last_run_at: datetime | None = None
    last_status: str | None = None
    last_error: str | None = None


class SourceConfigUpdate(BaseModel):
    enabled: bool | None = None
    schedule_minutes: int | None = Field(default=None, ge=5)


class ArticleRead(BaseModel):
    id: str
    source_key: str
    source_name: str
    title: str
    url: str
    published_at: datetime | None
    is_candidate: bool
    is_major_event: bool
    event_category: str | None
    event_importance: int | None
    core_summary: str | None
    filter_reason: str | None
    content_access: str
    llm_status: str
    translation_status: str
    display_title: str
    display_summary: str
    original_language: str
    is_foreign_original: bool
    included_in_today_digest: bool


class ArticleDetailRead(ArticleRead):
    summary_hint: str | None = None
    content_text: str | None = None
    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    rule_category: str | None = None
    dedupe_key: str | None = None
    analysis_payload: dict[str, Any] | None = None
    translated_title_zh: str | None = None
    translated_summary_zh: str | None = None
    translated_content_zh: str | None = None
    translated_at: datetime | None = None
    preserved_terms: list[str] = Field(default_factory=list)
    original_title: str
    original_summary: str | None = None
    original_content: str | None = None
    display_content: str | None = None
    included_in_latest_report: bool = False


class ArticleTranslationRead(BaseModel):
    article_id: str
    translation_status: str
    translated_title_zh: str | None = None
    translated_summary_zh: str | None = None
    translated_content_zh: str | None = None
    translated_at: datetime | None = None
    preserved_terms: list[str] = Field(default_factory=list)


class SourceRunLogRead(ORMBaseModel):
    id: str
    run_id: str
    source_key: str
    source_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    collected_count: int
    candidate_count: int
    analyzed_count: int
    translated_count: int
    error_message: str | None


class RunStageLogRead(ORMBaseModel):
    id: str
    run_id: str
    stage_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    processed_count: int
    error_message: str | None


class PipelineRunRead(ORMBaseModel):
    id: str
    trigger_mode: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    source_count: int
    collected_count: int
    candidate_count: int
    analyzed_count: int
    report_id: str | None
    error_message: str | None


class PipelineRunDetailRead(PipelineRunRead):
    source_logs: list[SourceRunLogRead] = Field(default_factory=list)
    stage_logs: list[RunStageLogRead] = Field(default_factory=list)


class DailyReportRead(ORMBaseModel):
    id: str
    report_date: date
    generated_at: datetime
    source_count: int
    major_event_count: int


class DashboardTopEventRead(BaseModel):
    id: str
    display_title: str
    display_summary: str
    source_key: str
    source_name: str
    url: str
    published_at: datetime | None = None
    published_at_label: str
    event_category: str | None = None
    event_category_label: str
    event_importance: int | None = None
    content_access: str
    content_access_label: str
    is_foreign_original: bool
    language: str
    included_in_today_digest: bool


class BriefingWindowRead(BaseModel):
    edition_date: str
    timezone: str
    cutoff_label: str
    start_at: str
    end_at: str
    start_label: str
    end_label: str
    label: str
    duration_hours: int


class BriefingTotalsRead(BaseModel):
    article_count: int
    candidate_count: int
    major_count: int
    source_count: int
    domestic_major_count: int
    foreign_major_count: int


class DashboardRunStatusRead(BaseModel):
    run_count: int
    success_count: int
    failed_count: int
    running_count: int
    latest_run_started_at: str | None = None
    latest_run_status: str
    latest_run_label: str


class SourceDistributionRead(BaseModel):
    source_key: str
    source_name: str
    article_count: int
    candidate_count: int
    major_count: int
    latest_published_at: str | None = None


class StrategicJudgementRead(BaseModel):
    title: str
    summary: str
    business_relevance: str
    impact_direction: str
    validation_focus: list[str] = Field(default_factory=list)
    watchpoints: list[str] = Field(default_factory=list)
    evidence_sources: list[str] = Field(default_factory=list)


class DashboardTodayRead(BaseModel):
    digest_id: str
    edition_date: str
    updated_at: str
    briefing_window: BriefingWindowRead
    briefing_totals: BriefingTotalsRead
    briefing_judgement: str
    strategic_judgement: StrategicJudgementRead
    top_events: list[DashboardTopEventRead]
    followup_events: list[DashboardTopEventRead]
    risk_signals: list[str]
    opportunity_signals: list[str]
    source_distribution: list[SourceDistributionRead]
    run_status: DashboardRunStatusRead


class SourceStatusRead(BaseModel):
    source_key: str
    source_name: str
    collector_kind: str
    schedule_minutes: int
    enabled: bool
    last_run_at: datetime | None = None
    last_status: str
    last_error: str | None = None
    edition_article_count: int
    edition_candidate_count: int
    edition_major_count: int
    latest_collected_count: int
    latest_candidate_count: int
    latest_analyzed_count: int
    latest_translated_count: int
    latest_duration_ms: int | None = None


class CollectRequest(BaseModel):
    source_keys: list[str] | None = None
    analyze: bool = True
    translate: bool = True
    build_digest: bool = True
    render_report: bool = False
    limit_per_source: int | None = Field(default=None, ge=1, le=50)
    trigger_mode: str = "manual"


class AnalyzeRequest(BaseModel):
    article_ids: list[str] | None = None


class GenerateReportRequest(BaseModel):
    report_date: date | None = None
