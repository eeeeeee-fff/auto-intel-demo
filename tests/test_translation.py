from app.models import ArticleORM
from app.services.translation import parse_translation_payload, reset_translation_if_needed


def test_reset_translation_for_changed_non_chinese_article() -> None:
    article = ArticleORM(
        source_key="just_auto",
        source_name="Just Auto",
        url="https://example.com/a",
        title="Example",
        language="en",
        translation_status="done",
        translated_title_zh="示例",
        translated_summary_zh="摘要",
        translated_content_zh="正文",
        translation_payload='{"preserved_terms":["PHEV"]}',
    )

    reset_translation_if_needed(article, content_changed=True)

    assert article.translation_status == "not_requested"
    assert article.translated_title_zh is None
    assert article.translation_payload is None


def test_parse_translation_payload_handles_json() -> None:
    payload = parse_translation_payload('{"preserved_terms":["PHEV","ADAS"]}')
    assert payload["preserved_terms"] == ["PHEV", "ADAS"]
