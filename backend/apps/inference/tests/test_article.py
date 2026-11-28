"""Reading an article out of a page: metadata, main text, page furniture
left out, pasted text, and the guard on where a link may point."""

import pytest

from apps.inference import article
from apps.inference.article import (
    ArticleError,
    article_from_text,
    extract_html,
    extract_markdown,
    read_article,
)

PAGE = """<!doctype html><html><head>
<title>Why lighthouses still matter | The Harbour Review</title>
<meta property="og:site_name" content="The Harbour Review">
<meta name="author" content="Ada Marsh">
<meta property="article:published_time" content="2026-03-04T09:00:00Z">
</head><body>
<nav><a href="/">Home</a><a href="/essays">Essays</a><p>This navigation paragraph is long enough to look like content but is not.</p></nav>
<header><p>Subscribe to our newsletter for more stories like this one every week.</p></header>
<main><article>
<h1>Why lighthouses still matter</h1>
<p>Ships have satellite positioning now, and yet the lights along the coast are still lit every single night.</p>
<div class="share-buttons"><p>Share this article with your friends on every network you can think of.</p></div>
<h2>A second system</h2>
<p>The reason is redundancy. When the electronics fail, a light on a headland is still exactly where the chart says it is.</p>
<blockquote>A light that never moves is worth more than a map that might.</blockquote>
<ul><li>They need no signal.</li><li>They need no subscription.</li></ul>
<p>That is why keepers, now mostly engineers, still climb the stairs to check the lamp before the autumn storms arrive.</p>
</article></main>
<aside><p>Related: ten other things you could be reading instead of finishing this page.</p></aside>
<footer><p>Copyright The Harbour Review. All rights reserved, including the long ones.</p></footer>
</body></html>"""


def test_html_metadata_and_main_text():
    a = extract_html(PAGE, "https://harbour.example/essays/lighthouses")
    assert a.title == "Why lighthouses still matter"
    assert a.author == "Ada Marsh"
    assert a.published == "2026-03-04"
    assert a.site == "The Harbour Review"
    kinds = [b.kind for b in a.blocks]
    assert kinds == ["paragraph", "heading", "paragraph", "quote", "item", "item", "paragraph"]
    text = " ".join(b.text for b in a.blocks)
    assert "redundancy" in text and "climb the stairs" in text


def test_html_leaves_out_page_furniture():
    text = " ".join(b.text for b in extract_html(PAGE, "https://harbour.example/x").blocks)
    for junk in ("navigation paragraph", "Subscribe to our newsletter", "Share this article", "Related:", "Copyright"):
        assert junk not in text
    # The headline is the title, not the first thing read aloud.
    assert not text.startswith("Why lighthouses still matter")


def test_byline_line_becomes_author_and_date():
    md = (
        "[Essays](https://x.example/essays)\n\nThe quiet coast\n===============\n\n"
        "**Ada Marsh**  ·  November 24, 2026  ·  3 min read\n\n"
        + "A long enough first paragraph about the coast at night, with lamps. " * 3
        + "\n\nAnd a second paragraph with a [link](https://x.example/a) in it.\n"
    )
    a = extract_markdown(md, "https://x.example/essays/quiet-coast")
    assert a.title == "The quiet coast"
    assert a.author == "Ada Marsh"
    assert a.published == "2026-11-24"
    assert [b.kind for b in a.blocks] == ["paragraph", "paragraph"]
    assert a.blocks[1].text == "And a second paragraph with a link in it."


def test_pasted_text_takes_a_short_first_line_as_title():
    a = article_from_text("On porch lights\n\nFirst paragraph here.\n\nSecond one.")
    assert a.title == "On porch lights"
    assert [b.text for b in a.blocks] == ["First paragraph here.", "Second one."]
    with pytest.raises(ArticleError):
        article_from_text("   \n  ")


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/secret", "http://localhost:8000/", "http://10.0.0.5/", "http://169.254.169.254/latest/",
    "http://[::1]/", "ftp://example.com/file",
])
def test_private_and_non_web_links_are_refused(url):
    with pytest.raises(ArticleError):
        article._check_public(url)


def test_scrape_result_is_used_when_good_and_fetch_is_the_fallback(monkeypatch):
    md = "# Title here\n\n" + "A sentence of scraped article text that goes on for a while. " * 20
    calls = []
    monkeypatch.setattr(article, "_fetch", lambda url: calls.append(url) or (url, PAGE))
    a = read_article("https://harbour.example/essays/lighthouses", scrape=lambda url: (md, {"title": "Title here"}))
    assert a.via == "scrape" and not calls
    # A scrape service that fails or returns nothing falls back to fetching.
    a = read_article("harbour.example/essays/lighthouses", scrape=lambda url: None)
    assert a.via == "fetch" and calls == ["https://harbour.example/essays/lighthouses"]
    assert a.source_url == "https://harbour.example/essays/lighthouses"


def test_hacker_news_link_is_followed_to_the_story(monkeypatch):
    class Resp:
        def json(self):
            return {"url": "https://harbour.example/essays/lighthouses", "title": "Why lighthouses still matter"}

    monkeypatch.setattr(article.requests, "get", lambda *a, **k: Resp())
    monkeypatch.setattr(article, "_fetch", lambda url: (url, PAGE))
    a = read_article("https://news.ycombinator.com/item?id=123456")
    assert a.url == "https://harbour.example/essays/lighthouses"
    assert a.source_url == "https://news.ycombinator.com/item?id=123456"
    assert a.author == "Ada Marsh"
