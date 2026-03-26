from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SourceConfigORM(Base):
    __tablename__ = "source_configs"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    collector_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    schedule_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(32))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class PipelineRunORM(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    trigger_mode: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    collected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    analyzed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    report_id: Mapped[str | None] = mapped_column(String(36))
    error_message: Mapped[str | None] = mapped_column(Text)


class RunStageLogORM(Base):
    __tablename__ = "run_stage_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("pipeline_runs.id"), nullable=False, index=True)
    stage_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)


class SourceRunLogORM(Base):
    __tablename__ = "source_run_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("pipeline_runs.id"), nullable=False, index=True)
    source_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    collected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    analyzed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    translated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)


class ArticleORM(Base):
    __tablename__ = "articles"
    __table_args__ = (UniqueConstraint("source_key", "url", name="uq_source_url"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    raw_html: Mapped[str | None] = mapped_column(Text)
    content_text: Mapped[str | None] = mapped_column(Text)
    summary_hint: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(256))
    tags_json: Mapped[str | None] = mapped_column(Text)
    content_access: Mapped[str] = mapped_column(String(32), default="full_text", nullable=False)
    rule_category: Mapped[str | None] = mapped_column(String(64))
    is_candidate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    filter_reason: Mapped[str | None] = mapped_column(Text)
    llm_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    translation_status: Mapped[str] = mapped_column(String(32), default="not_requested", nullable=False)
    event_category: Mapped[str | None] = mapped_column(String(64))
    event_importance: Mapped[int | None] = mapped_column(Integer)
    is_major_event: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    core_summary: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(String(512), index=True)
    analysis_payload: Mapped[str | None] = mapped_column(Text)
    translated_title_zh: Mapped[str | None] = mapped_column(Text)
    translated_summary_zh: Mapped[str | None] = mapped_column(Text)
    translated_content_zh: Mapped[str | None] = mapped_column(Text)
    translation_payload: Mapped[str | None] = mapped_column(Text)
    translated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    included_in_today_digest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    digest_rank: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class TodayDigestORM(Base):
    __tablename__ = "today_digests"
    __table_args__ = (UniqueConstraint("digest_date", "timezone", name="uq_digest_date_timezone"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    digest_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai", nullable=False)
    window_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary_payload: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("pipeline_runs.id"))
    source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    article_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    major_event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class DailyReportORM(Base):
    __tablename__ = "daily_reports"
    __table_args__ = (UniqueConstraint("report_date", name="uq_report_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    html: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    major_event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
