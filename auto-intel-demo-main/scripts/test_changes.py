"""Verify all pipeline changes (Steps 1-3)."""
from __future__ import annotations

import inspect
import sys

sys.path.insert(0, ".")

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} -- {detail}")


# === Step 1: Timeout separation ===
print("\n[Step 1] Timeout separation")
from app.config import get_settings

s = get_settings()
check("request_timeout_seconds == 20", s.request_timeout_seconds == 20)
check("llm_timeout_seconds == 120", s.llm_timeout_seconds == 120)

# === Step 2: Chinese prompt + LLM timeout wired ===
print("\n[Step 2] Chinese prompt in analyze_article + LLM timeout wired")
from app.services.llm import DeepSeekClient

src_analyze = inspect.getsource(DeepSeekClient.analyze_article)
check("core_summary Chinese instruction present", "\u7b80\u4f53\u4e2d\u6587" in src_analyze)

src_init = inspect.getsource(DeepSeekClient.__init__)
check("llm_timeout_seconds used in __init__", "llm_timeout_seconds" in src_init)
check("request_timeout_seconds NOT in __init__", "request_timeout_seconds" not in src_init)

# === Step 3: Formatting module ===
print("\n[Step 3] Formatting module")
from app.services.formatting import clean_lines, format_content, strip_noise_elements
from bs4 import BeautifulSoup

# 3a: strip_noise_elements
html = (
    "<html><body>"
    '<nav>Menu</nav>'
    '<article><p>Important automotive content here for testing purposes.</p></article>'
    '<footer>Copyright 2024</footer>'
    '<div class="cookie-banner">We use cookies</div>'
    '<aside>Sidebar</aside>'
    "</body></html>"
)
soup = BeautifulSoup(html, "html.parser")
strip_noise_elements(soup)
text = soup.get_text()
check("nav removed", "Menu" not in text)
check("footer removed", "Copyright" not in text)
check("cookie-banner removed", "cookie" not in text.lower())
check("aside removed", "Sidebar" not in text)
check("article content kept", "Important automotive" in text)

# 3b: clean_lines
sample = (
    "Cookie policy here\n"
    "Important automotive news line that is long enough.\n"
    "Share\n"
    "Related Articles\n"
    "\u00a9 2024 All rights reserved\n"
    "Another valid line of automotive news content."
)
result = clean_lines(sample)
check("cookie line removed", "Cookie" not in result)
check("share line removed", "Share" not in result)
check("related articles removed", "Related Articles" not in result)
check("copyright removed", "\u00a9 2024" not in result)
check("valid lines kept", "Important automotive" in result and "Another valid" in result)

# 3c: format_content
check(
    "collapses blank lines",
    format_content("Line one.\n\n\n\n\nLine two.") == "Line one.\n\nLine two.",
)

# 3d: integration in base.py
print("\n[Step 3d] Integration in collectors/base.py")
src_base = inspect.getsource(
    __import__("app.collectors.base", fromlist=["BaseCollector"]).BaseCollector.build_article_from_html
)
check("strip_noise_elements called", "strip_noise_elements" in src_base)
check("format_content wraps extract_main_text", "format_content" in src_base)

# === Step 5: Reprocess script importable ===
print("\n[Step 5] Reprocess script")
try:
    from scripts.reprocess_articles import main as _reprocess_main  # noqa: F401
    check("reprocess_articles importable", True)
except Exception as e:
    check("reprocess_articles importable", False, str(e))

# === Summary ===
print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
if failed:
    sys.exit(1)
