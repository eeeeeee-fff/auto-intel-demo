from __future__ import annotations

import json
from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ArticleORM, SourceConfigORM, TodayDigestORM, utc_now
from app.services.reporting import (
    CATEGORY_LABELS,
    CONTENT_ACCESS_LABELS,
    build_source_stats,
    build_time_window_context,
    load_major_articles,
    load_runs,
    load_source_run_logs,
    load_source_runs,
    load_stage_logs,
    query_articles,
)
from app.services.time_windows import (
    BriefingWindow,
    briefing_window,
    current_briefing_edition_date,
    followup_window,
    format_shanghai,
)
from app.services.translation import article_display_summary, article_display_title, is_foreign_original


DOMESTIC_SOURCE_KEYS = {"cnautonews", "gasgoo", "xinhua_auto"}
OPPORTUNITY_CATEGORIES = {"strategic_cooperation", "technology_breakthrough", "sales_data"}
RISK_CATEGORIES = {"policy_regulation", "macro_policy", "geopolitics", "commodities_fx", "incident", "supply_chain"}

WATCHPOINT_LABELS = {
    "technology_breakthrough": "中国 OEM 混动 / 增程平台与技术路线推进",
    "strategic_cooperation": "重点客户新平台合作与定点节奏",
    "sales_data": "销量变化是否转化为平台扩产与项目释放",
    "supply_chain": "供应链降本、本地化与交付稳定性",
    "policy_regulation": "排放、关税与监管政策对区域需求的传导",
    "macro_policy": "能源与产业政策变化对区域投资节奏的影响",
    "geopolitics": "区域贸易壁垒与本地化采购变化",
    "commodities_fx": "HDPE、钢材、汇率与能源成本传导",
    "incident": "海外供应链突发事件对交付与库存的影响",
    "executive_change": "核心客户高层调整对平台战略的影响",
}


def _target_edition_date(value: date | None) -> date:
    return value or current_briefing_edition_date()


def _serialize_window(window: BriefingWindow) -> dict[str, Any]:
    return {
        "edition_date": window.edition_date.isoformat(),
        "timezone": window.timezone,
        "cutoff_label": window.cutoff_label,
        "start_at": window.start_at.isoformat(),
        "end_at": window.end_at.isoformat(),
        "start_label": format_shanghai(window.start_at),
        "end_label": format_shanghai(window.end_at),
        "label": window.label,
        "duration_hours": window.duration_hours,
    }


def _serialize_event(article: ArticleORM) -> dict[str, Any]:
    return {
        "id": article.id,
        "display_title": article_display_title(article),
        "display_summary": article_display_summary(article),
        "source_key": article.source_key,
        "source_name": article.source_name,
        "url": article.url,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "published_at_label": format_shanghai(article.published_at),
        "event_category": article.event_category,
        "event_category_label": CATEGORY_LABELS.get(article.event_category or "", article.event_category or "未分类"),
        "event_importance": article.event_importance,
        "content_access": article.content_access,
        "content_access_label": CONTENT_ACCESS_LABELS.get(article.content_access, article.content_access),
        "is_foreign_original": is_foreign_original(article),
        "language": article.language,
        "included_in_today_digest": article.included_in_today_digest,
    }


def _empty_digest_payload(window: BriefingWindow) -> dict[str, Any]:
    return {
        "edition_date": window.edition_date.isoformat(),
        "updated_at": format_shanghai(utc_now()),
        "briefing_window": _serialize_window(window),
        "briefing_totals": {
            "article_count": 0,
            "candidate_count": 0,
            "major_count": 0,
            "source_count": 0,
            "domestic_major_count": 0,
            "foreign_major_count": 0,
        },
        "briefing_judgement": "本期窗口内暂无达到重大事件阈值的公开资讯，建议优先检查来源运行、发布时间落点和候选阈值。",
        "strategic_judgement": {
            "title": "外部信号不足，今天以核实为主",
            "summary": (
                "本期窗口内暂无足够的重大事件形成稳定判断。"
                " 对亚普这类覆盖燃油系统、高压油箱与热管理的零部件企业，今天更适合先核实来源运行、客户平台节奏和区域需求变化。"
            ),
            "business_relevance": "低",
            "impact_direction": "中性观察",
            "validation_focus": ["客户平台", "区域布局", "成本传导"],
            "watchpoints": ["重点客户平台节奏", "区域需求变化", "材料与汇率传导"],
            "evidence_sources": [],
        },
        "top_events": [],
        "followup_events": [],
        "risk_signals": ["当前未识别到需要升级处理的高等级风险项。"],
        "opportunity_signals": ["当前未识别到需要升级处理的机会项。"],
        "source_distribution": [],
        "run_status": {
            "run_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "running_count": 0,
            "latest_run_started_at": None,
            "latest_run_status": "idle",
            "latest_run_label": "本期窗口内暂无任务执行记录",
        },
    }


def _impact_direction_label(articles: list[ArticleORM]) -> str:
    opportunity_score = sum(
        (article.event_importance or 3)
        for article in articles
        if article.event_category in OPPORTUNITY_CATEGORIES
    )
    risk_score = sum(
        (article.event_importance or 3)
        for article in articles
        if article.event_category in RISK_CATEGORIES
    )
    if opportunity_score and risk_score:
        if abs(opportunity_score - risk_score) <= 3:
            return "分化"
        return "潜在利好" if opportunity_score > risk_score else "潜在承压"
    if opportunity_score:
        return "潜在利好"
    if risk_score:
        return "潜在承压"
    return "中性观察"


def _business_relevance_label(articles: list[ArticleORM]) -> str:
    if not articles:
        return "低"
    weighted_score = sum(article.event_importance or 3 for article in articles)
    if weighted_score >= 18 or any((article.event_importance or 0) >= 4 for article in articles[:3]):
        return "高"
    if weighted_score >= 8:
        return "中"
    return "低"


def _validation_focus(articles: list[ArticleORM]) -> list[str]:
    categories = {article.event_category for article in articles if article.event_category}
    focus: list[str] = []
    if categories & {"technology_breakthrough", "strategic_cooperation", "sales_data"}:
        focus.append("客户平台")
    if categories & {"technology_breakthrough"}:
        focus.append("技术路线")
    if categories & {"policy_regulation", "macro_policy", "geopolitics"}:
        focus.append("区域布局")
    if categories & {"commodities_fx", "supply_chain", "incident"}:
        focus.append("成本传导")
    defaults = ["客户平台", "区域布局", "成本传导"]
    for item in defaults:
        if item not in focus:
            focus.append(item)
    return focus[:3]


def _watchpoints(articles: list[ArticleORM]) -> list[str]:
    counts = Counter(article.event_category for article in articles if article.event_category)
    watchpoints: list[str] = []
    for category, _ in counts.most_common():
        label = WATCHPOINT_LABELS.get(category or "")
        if label and label not in watchpoints:
            watchpoints.append(label)

    fallback_items = [
        "重点客户平台节奏是否加快",
        "欧洲业务暴露与区域本地化变化",
        "HDPE、钢材、汇率与能源成本传导",
    ]
    for item in fallback_items:
        if item not in watchpoints:
            watchpoints.append(item)
    return watchpoints[:3]


def _lead_phrase(categories: list[str], direction: str) -> str:
    top_category = categories[0] if categories else None
    if direction == "分化":
        if top_category in {"technology_breakthrough", "strategic_cooperation"}:
            return "今日外部信号显示，新能源与平台投入仍在推进，但区域经营压力并未同步缓解。"
        if top_category in {"sales_data"}:
            return "今日外部信号显示，平台机会仍在释放，但区域分化与海外压力也在同步扩大。"
        return "今日外部信号显示，机会与压力正在同时抬升，外部环境继续分化。"
    if direction == "潜在利好":
        if top_category in {"technology_breakthrough", "strategic_cooperation"}:
            return "今日外部信号显示，技术与平台投入延续，客户侧机会仍在继续打开。"
        if top_category in {"sales_data"}:
            return "今日外部信号显示，销量与平台信号偏积极，客户项目释放预期仍在抬升。"
        return "今日外部信号显示，外部机会信号偏多，平台推进节奏仍在延续。"
    if direction == "潜在承压":
        if top_category in {"policy_regulation", "macro_policy", "geopolitics", "commodities_fx", "supply_chain"}:
            return "今日外部信号显示，政策、成本与区域供应链扰动仍在抬升。"
        return "今日外部信号显示，外部扰动仍在增强，短期压力尚未缓解。"
    return "今日外部信号有限，当前更适合以观察与核实为主。"


def _strategic_title(articles: list[ArticleORM], direction: str) -> str:
    """生成通俗易懂的战略判断标题"""
    categories = [article.event_category for article in articles if article.event_category]
    category_counts = Counter(categories)
    top_category = category_counts.most_common(1)[0][0] if category_counts else None
    domestic_count = len([article for article in articles if article.source_key in DOMESTIC_SOURCE_KEYS])
    foreign_count = len([article for article in articles if article.source_key not in DOMESTIC_SOURCE_KEYS])

    # 使用更通俗易懂的表达方式
    if direction == "分化" and domestic_count and foreign_count:
        return "国内机会增多，海外压力仍存"
    if direction == "分化":
        if top_category in {"technology_breakthrough", "strategic_cooperation"}:
            return "技术投入加大，但区域差异明显"
        if top_category == "sales_data":
            return "销量增长，但市场分化加剧"
        return "机会与压力并存，市场持续分化"
    if direction == "潜在利好":
        if top_category == "technology_breakthrough":
            return "技术平台持续投入，市场机会增加"
        if top_category == "sales_data":
            return "销量好转，客户订单机会增多"
        return "市场信号积极，发展机会提升"
    if direction == "潜在承压":
        if top_category in {"policy_regulation", "macro_policy", "geopolitics", "commodities_fx", "supply_chain"}:
            return "政策成本压力加大，外部风险上升"
        return "外部扰动增加，短期仍有压力"
    return "市场信号不明显，今天以观察为主"


def _build_strategic_judgement(articles: list[ArticleORM], window: BriefingWindow) -> dict[str, Any]:
    if not articles:
        return _empty_digest_payload(window)["strategic_judgement"]

    counts = Counter(article.event_category or "incident" for article in articles)
    direction = _impact_direction_label(articles)
    validation_focus = _validation_focus(articles)
    watchpoints = _watchpoints(articles)
    categories = [key for key, _ in counts.most_common(3)]

    lead_phrase = _lead_phrase(categories, direction)
    if direction == "分化":
        impact_phrase = "平台机会与区域成本压力可能同时存在。"
    elif direction == "潜在利好":
        impact_phrase = "客户平台与技术配套机会可能继续打开。"
    elif direction == "潜在承压":
        impact_phrase = "海外成本、区域调整与客户降本压力仍需警惕。"
    else:
        impact_phrase = "短期信号仍以观察和验证为主。"

    summary = (
        f"{lead_phrase}"
        " 对亚普这类覆盖燃油系统、高压油箱与热管理的零部件企业，"
        f"这意味着{impact_phrase}"
        f" 今天更值得内部核实的是：{'、'.join(watchpoints)}。"
    )
    evidence_sources = []
    for article in articles[:3]:
        if article.source_name not in evidence_sources:
            evidence_sources.append(article.source_name)

    return {
        "title": _strategic_title(articles, direction),
        "summary": summary,
        "business_relevance": _business_relevance_label(articles),
        "impact_direction": direction,
        "validation_focus": validation_focus,
        "watchpoints": watchpoints,
        "evidence_sources": evidence_sources,
    }


def _build_judgement(articles: list[ArticleORM], window: BriefingWindow) -> tuple[str, list[str], list[str], dict[str, Any]]:
    if not articles:
        payload = _empty_digest_payload(window)
        strategic = payload["strategic_judgement"]
        return strategic["summary"], payload["risk_signals"], payload["opportunity_signals"], strategic

    risk_pool = [
        article_display_title(item)
        for item in articles
        if item.event_category in {"policy_regulation", "macro_policy", "geopolitics", "commodities_fx", "incident", "supply_chain"}
        and (item.event_importance or 0) >= 4
    ]
    opportunity_pool = [
        article_display_title(item)
        for item in articles
        if item.event_category in {"strategic_cooperation", "technology_breakthrough", "sales_data"}
        and (item.event_importance or 0) >= 4
    ]
    risk_signals = risk_pool[:3] or ["当前窗口内暂无高等级风险项，但仍需继续盯住政策与供应链波动。"]
    opportunity_signals = opportunity_pool[:3] or ["当前窗口内暂无高等级机会项，可通过持续跟踪补足趋势判断。"]
    strategic = _build_strategic_judgement(articles, window)
    return strategic["summary"], risk_signals, opportunity_signals, strategic


def _build_run_status(session: Session, window: BriefingWindow) -> dict[str, Any]:
    runs = load_runs(session, target_date=window.edition_date, window_mode="edition", limit=20)
    if not runs:
        return _empty_digest_payload(window)["run_status"]

    latest = runs[0]
    return {
        "run_count": len(runs),
        "success_count": len([run for run in runs if run.status == "success"]),
        "failed_count": len([run for run in runs if run.status == "failed"]),
        "running_count": len([run for run in runs if run.status == "running"]),
        "latest_run_started_at": latest.started_at.isoformat() if latest.started_at else None,
        "latest_run_status": latest.status,
        "latest_run_label": f"{format_shanghai(latest.started_at)} / {latest.status}",
    }


def _displayable_articles(articles: list[ArticleORM]) -> list[ArticleORM]:
    return [item for item in articles if item.language == "zh" or item.translation_status == "done"]


def _build_followup_events(session: Session, window: BriefingWindow, current_articles: list[ArticleORM]) -> list[ArticleORM]:
    settings = get_settings()
    start_at, end_at = followup_window(window.edition_date, days=settings.briefing_followup_days)
    historical = load_major_articles(
        session,
        window_start_at=start_at,
        window_end_at=end_at,
    )
    current_keys = {item.dedupe_key or item.title for item in current_articles}
    followups: list[ArticleORM] = []
    for article in _displayable_articles(historical):
        if (article.event_importance or 0) < 4:
            continue
        key = article.dedupe_key or article.title
        if key in current_keys:
            continue
        followups.append(article)
        current_keys.add(key)
        if len(followups) >= 2:
            break
    return followups


def build_today_digest(session: Session, *, target_date: date | None = None, run_id: str | None = None) -> TodayDigestORM:
    active_date = _target_edition_date(target_date)
    window = briefing_window(active_date)
    all_articles = query_articles(session, target_date=active_date, window_mode="edition", limit=1000)
    major_articles = load_major_articles(session, target_date=active_date, window_mode="edition")
    displayable_major_articles = _displayable_articles(major_articles)
    top_events = displayable_major_articles[:5]
    followup_events = _build_followup_events(session, window, top_events)
    judgement, risk_signals, opportunity_signals, strategic_judgement = _build_judgement(
        displayable_major_articles[:8], window
    )

    source_distribution = []
    for item in build_source_stats(all_articles):
        source_distribution.append(
            {
                **item,
                "latest_published_at": item["latest_published_at"].isoformat() if item["latest_published_at"] else None,
            }
        )
    run_status = _build_run_status(session, window)

    for article in all_articles:
        article.included_in_today_digest = False
        article.digest_rank = None
    for index, article in enumerate(top_events, start=1):
        article.included_in_today_digest = True
        article.digest_rank = index

    payload = {
        "edition_date": active_date.isoformat(),
        "updated_at": format_shanghai(utc_now()),
        "briefing_window": _serialize_window(window),
        "briefing_totals": {
            "article_count": len(all_articles),
            "candidate_count": len([item for item in all_articles if item.is_candidate]),
            "major_count": len(displayable_major_articles),
            "source_count": len({item.source_key for item in all_articles}),
            "domestic_major_count": len([item for item in displayable_major_articles if item.source_key in DOMESTIC_SOURCE_KEYS]),
            "foreign_major_count": len([item for item in displayable_major_articles if item.source_key not in DOMESTIC_SOURCE_KEYS]),
        },
        "briefing_judgement": judgement,
        "strategic_judgement": strategic_judgement,
        "top_events": [_serialize_event(item) for item in top_events],
        "followup_events": [_serialize_event(item) for item in followup_events],
        "risk_signals": risk_signals,
        "opportunity_signals": opportunity_signals,
        "source_distribution": source_distribution,
        "run_status": run_status,
    }

    digest = session.scalars(
        select(TodayDigestORM)
        .where(TodayDigestORM.digest_date == active_date)
        .where(TodayDigestORM.timezone == window.timezone)
    ).first()
    if digest is None:
        digest = TodayDigestORM(digest_date=active_date, timezone=window.timezone, summary_payload="{}")
        session.add(digest)

    digest.window_start_at = window.start_at
    digest.window_end_at = window.end_at
    digest.summary_payload = json.dumps(payload, ensure_ascii=False)
    digest.generated_at = utc_now()
    digest.run_id = run_id
    digest.source_count = payload["briefing_totals"]["source_count"]
    digest.article_count = payload["briefing_totals"]["article_count"]
    digest.major_event_count = payload["briefing_totals"]["major_count"]
    session.commit()
    session.refresh(digest)
    return digest


def load_today_digest(session: Session, target_date: date | None = None) -> TodayDigestORM | None:
    active_date = _target_edition_date(target_date)
    return session.scalars(
        select(TodayDigestORM)
        .where(TodayDigestORM.digest_date == active_date)
        .where(TodayDigestORM.timezone == briefing_window(active_date).timezone)
        .order_by(TodayDigestORM.generated_at.desc())
    ).first()


def parse_digest_payload(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def get_dashboard_today(session: Session, target_date: date | None = None) -> dict[str, Any]:
    active_date = _target_edition_date(target_date)
    digest = load_today_digest(session, active_date)
    if digest is None:
        digest = build_today_digest(session, target_date=active_date)
    payload = parse_digest_payload(digest.summary_payload)
    if not payload or "strategic_judgement" not in payload:
        digest = build_today_digest(session, target_date=active_date)
        payload = parse_digest_payload(digest.summary_payload)
    if not payload or "strategic_judgement" not in payload:
        payload = _empty_digest_payload(briefing_window(active_date))
    payload["digest_id"] = digest.id
    payload["edition_date"] = active_date.isoformat()
    return payload


def build_source_status(session: Session, target_date: date | None = None) -> list[dict[str, Any]]:
    active_date = _target_edition_date(target_date)
    articles = query_articles(session, target_date=active_date, window_mode="edition", limit=1000)
    stats_map = {item["source_key"]: item for item in build_source_stats(articles)}
    sources = list(session.scalars(select(SourceConfigORM).order_by(SourceConfigORM.key)))
    rows: list[dict[str, Any]] = []
    for source in sources:
        recent_logs = load_source_runs(session, source.key, limit=1)
        latest_log = recent_logs[0] if recent_logs else None
        stat = stats_map.get(source.key, {})
        rows.append(
            {
                "source_key": source.key,
                "source_name": source.name,
                "collector_kind": source.collector_kind,
                "schedule_minutes": source.schedule_minutes,
                "enabled": source.enabled,
                "last_run_at": source.last_run_at,
                "last_status": source.last_status or "idle",
                "last_error": source.last_error,
                "edition_article_count": int(stat.get("article_count", 0)),
                "edition_candidate_count": int(stat.get("candidate_count", 0)),
                "edition_major_count": int(stat.get("major_count", 0)),
                "latest_collected_count": latest_log.collected_count if latest_log else 0,
                "latest_candidate_count": latest_log.candidate_count if latest_log else 0,
                "latest_analyzed_count": latest_log.analyzed_count if latest_log else 0,
                "latest_translated_count": latest_log.translated_count if latest_log else 0,
                "latest_duration_ms": latest_log.duration_ms if latest_log else None,
            }
        )
    return rows


def render_ops_context(session: Session, *, target_date: date | None = None) -> dict[str, Any]:
    active_date = _target_edition_date(target_date)
    window_context = build_time_window_context(active_date, window_mode="edition")
    runs = load_runs(session, target_date=active_date, window_mode="edition", limit=20)
    latest_run = runs[0] if runs else None
    latest_source_logs = load_source_run_logs(session, latest_run.id) if latest_run else []
    latest_stage_logs = load_stage_logs(session, latest_run.id) if latest_run else []
    return {
        "active_date": active_date,
        "window_info": window_context,
        "source_status": build_source_status(session, active_date),
        "runs": runs,
        "latest_run": latest_run,
        "latest_source_logs": latest_source_logs,
        "latest_stage_logs": latest_stage_logs,
    }


def render_dashboard_context(session: Session, *, target_date: date | None = None) -> dict[str, Any]:
    payload = get_dashboard_today(session, target_date)
    active_date = _target_edition_date(target_date)
    source_status = build_source_status(session, active_date)
    payload["active_date"] = active_date
    payload["window_info"] = payload.get("briefing_window") or build_time_window_context(active_date, window_mode="edition")
    payload["hero_event"] = payload["top_events"][0] if payload.get("top_events") else None
    payload["source_status"] = source_status
    payload["source_health"] = {
        "success_count": len([item for item in source_status if item["last_status"] == "success"]),
        "failed_count": len([item for item in source_status if item["last_status"] == "failed"]),
        "running_count": len([item for item in source_status if item["last_status"] == "running"]),
        "idle_count": len([item for item in source_status if item["last_status"] not in {"success", "failed", "running"}]),
    }
    return payload
