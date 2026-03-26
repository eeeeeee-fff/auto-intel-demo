from app.collectors.sources import JustAutoCollector, MarkLinesCollector


class FakeResponse:
    def __init__(self, text: str, content_type: str = "text/html; charset=utf-8") -> None:
        self.text = text
        self.headers = {"Content-Type": content_type}
        self.apparent_encoding = "utf-8"

    def raise_for_status(self) -> None:
        return None


def test_just_auto_collector_builds_summary_hint_from_article(monkeypatch) -> None:
    collector = JustAutoCollector()
    listing_html = """
    <html>
      <body>
        <a href="https://www.just-auto.com/news/example-strategy-shift/">Strategy shift</a>
      </body>
    </html>
    """
    article_html = """
    <html>
      <head>
        <title>Supplier strategy shift</title>
        <meta property="article:published_time" content="2026-03-18T08:00:00+00:00" />
      </head>
      <body>
        <article>
          <p>The supplier is expanding hybrid and combustion component production after new orders increased.</p>
          <p>The move affects refinancing, manufacturing footprint and future platform sourcing.</p>
        </article>
      </body>
    </html>
    """

    def fake_request(url: str) -> FakeResponse:
        if url == collector.news_url:
            return FakeResponse(listing_html)
        if url == "https://www.just-auto.com/news/example-strategy-shift/":
            return FakeResponse(article_html)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(collector, "request", fake_request)

    articles = collector.collect(limit=3)
    assert len(articles) == 1
    assert articles[0].title == "Supplier strategy shift"
    assert "expanding hybrid" in articles[0].content_text
    assert articles[0].summary_hint
    assert articles[0].content_access == "full_text"


def test_marklines_collector_uses_index_only_cards(monkeypatch) -> None:
    collector = MarkLinesCollector()
    listing_html = """
    <html>
      <body>
        <article class="simplified-news-card">
          <div class="news-card-text-area">
            <header>
              <hgroup>
                <h3 class="news-title">
                  <a href="/en/news/341818" class="news-card-link">GM, LGES to supply LFP batteries</a>
                </h3>
              </hgroup>
            </header>
            <a href="/en/news/341818" class="news-card-link">
              <p class="news-body">Ultium Cells will rehire workers to start LFP cell production in April.</p>
            </a>
            <div class="meta-info-group">
              <time itemprop="datePublished" datetime="2026-03-18T06:02:00Z">Mar 18, 2026</time>
              <ul class="tag-group">
                <li><a href="/en/news/tag/13/gm">GM</a></li>
                <li><a href="/en/news/tag/363/lg-energy-solution">LG Energy Solution</a></li>
              </ul>
            </div>
          </div>
        </article>
      </body>
    </html>
    """

    def fake_request(url: str) -> FakeResponse:
        if url == collector.news_url:
            return FakeResponse(listing_html)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(collector, "request", fake_request)

    articles = collector.collect(limit=5)
    assert len(articles) == 1
    article = articles[0]
    assert article.url == "https://www.marklines.com/en/news/341818"
    assert article.title == "GM, LGES to supply LFP batteries"
    assert article.content_access == "index_only"
    assert article.summary_hint.startswith("Ultium Cells")
    assert article.tags == ["GM", "LG Energy Solution"]
