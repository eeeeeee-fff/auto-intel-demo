from datetime import datetime, timezone

from app.services.rules import apply_rule_filter, article_is_major, importance_is_major


def test_rule_filter_marks_supply_chain_event() -> None:
    decision = apply_rule_filter(
        title="某车企与供应商合作推进高压燃油系统国产替代",
        content_text="供应链重构与高压油箱项目落地，涉及材料成本、平台扩产与本地化采购。",
        summary_hint="",
        published_at=datetime.now(timezone.utc),
        lookback_hours=72,
        source_key="gasgoo",
    )
    assert decision.is_candidate is True
    assert decision.is_major_event is True
    assert decision.category in {"strategic_cooperation", "supply_chain"}


def test_rule_filter_rejects_noise_article() -> None:
    decision = apply_rule_filter(
        title="新车型亮相车展并公布试驾体验",
        content_text="新车亮相，外观升级，线下体验活动同步推出。",
        summary_hint="",
        published_at=datetime.now(timezone.utc),
        lookback_hours=72,
        source_key="xinhua_auto",
    )
    assert decision.is_candidate is False
    assert decision.filter_reason == "noise_article"


def test_rule_filter_rejects_autoweek_consumer_noise() -> None:
    decision = apply_rule_filter(
        title="2026 Audi Q3 First Drive: Better Than Ever",
        content_text="Our first drive reviews the new crossover from a consumer perspective.",
        summary_hint="",
        published_at=datetime.now(timezone.utc),
        lookback_hours=72,
        source_key="autoweek",
    )
    assert decision.is_candidate is False
    assert decision.filter_reason in {"noise_article", "source_specific_noise"}


def test_rule_filter_accepts_oica_digest_signal() -> None:
    decision = apply_rule_filter(
        title="03/17/2026: OICA's 5 major news items summarized",
        content_text=(
            "Trump tariffs have cost automakers at least $35 billion since 2025. "
            "Debate over the phase-out of internal combustion engines continues in Europe."
        ),
        summary_hint="",
        published_at=datetime.now(timezone.utc),
        lookback_hours=72,
        source_key="oica",
    )
    assert decision.is_candidate is True
    assert decision.is_major_event is True
    assert decision.category in {"policy_regulation", "macro_policy", "geopolitics"}


def test_importance_threshold_marks_major_from_three_stars() -> None:
    assert importance_is_major(2) is False
    assert importance_is_major(3) is True
    assert importance_is_major(5) is True

    class StubArticle:
        event_importance = 3
        is_major_event = False

    assert article_is_major(StubArticle()) is True
