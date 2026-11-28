"""Turn "something to read" into an article worth reading aloud.

``read_article(url)`` takes a link, any link: a page, or a Hacker News
discussion that points at one. It finds the real article, pulls out its title,
author, date and main text, and returns them as an ``Article`` whose ``blocks``
are headings and paragraphs in reading order, with navigation, footers, share
buttons and other page furniture left out.

Two ways to get the page, tried in order:

1. the club's own scrape service (Firecrawl on a member's machine), which
   renders JavaScript and returns clean markdown;
2. fetching the HTML directly and extracting the main content here.

The second exists so narration does not stop working when the scrape service
is down or cannot reach a page. Direct fetches are guarded against being
pointed at private addresses (``_check_public``).

``article_from_text(text)`` does the same job for pasted text.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlparse

import requests

MAX_BYTES = 3_000_000
TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; inference.club narration; +https://inference.club)"


class ArticleError(Exception):
    """The link could not be turned into an article. ``str(e)`` is safe to show."""


@dataclass
class Block:
    kind: str  # "heading" | "paragraph" | "quote" | "item"
    text: str


@dataclass
class Article:
    title: str = ""
    author: str = ""
    published: str = ""  # ISO date (YYYY-MM-DD) when one was found
    site: str = ""
    url: str = ""  # where the text finally came from
    source_url: str = ""  # what the person gave us (e.g. the HN link)
    via: str = ""  # "scrape" | "fetch" | "text"
    blocks: list[Block] = field(default_factory=list)

    @property
    def words(self) -> int:
        return sum(len(b.text.split()) for b in self.blocks)

    def as_dict(self) -> dict:
        return {
            "title": self.title, "author": self.author, "published": self.published,
            "site": self.site, "url": self.url, "source_url": self.source_url,
            "via": self.via, "words": self.words,
            "blocks": [{"kind": b.kind, "text": b.text} for b in self.blocks],
        }


# --- Fetching ---------------------------------------------------------------


def _check_public(url: str) -> None:
    """Refuse anything that is not plain http(s) to a public address, so a
    link cannot be used to reach the server's own network."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ArticleError("That does not look like a web link.")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror:
        raise ArticleError("That site could not be found.") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ArticleError("That link points at a private address.")


def _fetch(url: str) -> tuple[str, str]:
    """GET ``url`` following a few redirects, each one checked. Returns
    (final_url, html)."""
    for _ in range(5):
        _check_public(url)
        try:
            r = requests.get(
                url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"},
                timeout=TIMEOUT, allow_redirects=False, stream=True,
            )
        except requests.RequestException:
            raise ArticleError("The page could not be reached.") from None
        if r.is_redirect and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            r.close()
            continue
        if r.status_code >= 400:
            raise ArticleError(f"The page answered with an error ({r.status_code}).")
        body = b""
        for chunk in r.iter_content(65536):
            body += chunk
            if len(body) > MAX_BYTES:
                break
        r.close()
        return url, body.decode(r.encoding or "utf-8", errors="replace")
    raise ArticleError("The link redirected too many times.")


_HN_ITEM = re.compile(r"^(?:www\.)?news\.ycombinator\.com$")


def _resolve_hacker_news(url: str) -> tuple[str, str]:
    """A Hacker News discussion link → (the story's own link, its title).
    Returns ("", title) for text posts, which have no outside link."""
    parts = urlparse(url)
    item = parse_qs(parts.query).get("id", [""])[0]
    if not (_HN_ITEM.match(parts.hostname or "") and item.isdigit()):
        return url, ""
    try:
        data = requests.get(
            f"https://hacker-news.firebaseio.com/v0/item/{item}.json", timeout=TIMEOUT
        ).json() or {}
    except (requests.RequestException, ValueError):
        raise ArticleError("Hacker News could not be reached.") from None
    return data.get("url") or "", data.get("title") or ""


# --- Extraction from HTML ---------------------------------------------------

_SKIP = {"script", "style", "noscript", "template", "svg", "nav", "footer", "aside", "form",
         "button", "iframe", "figure", "figcaption", "select", "dialog", "menu"}
_VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr", "area", "base", "col", "embed", "track"}
_BLOCKS = {"p": "paragraph", "blockquote": "quote", "li": "item", "pre": "paragraph",
           "h1": "heading", "h2": "heading", "h3": "heading", "h4": "heading"}
# Class/id hints for page furniture that sits inside the main container.
_NOISE = re.compile(
    r"(^|[\s_-])(nav|menu|share|social|comment|related|sidebar|footer|subscribe|newsletter|"
    r"promo|advert|ad|cookie|breadcrumb|byline-links|tags?|toc)([\s_-]|$)", re.I)


class _Reader(HTMLParser):
    """One pass over the page collecting metadata and every text block, each
    tagged with the chain of containers it sits in."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self.jsonld: list[str] = []
        self.blocks: list[tuple[tuple[int, ...], str, str]] = []  # (container path, kind, text)
        self.times: list[str] = []
        self._stack: list[tuple[str, int, bool]] = []  # (tag, id, noisy)
        self._ids = 0
        self._skip = 0
        self._cur: list[str] | None = None
        self._cur_kind = ""
        self._cur_depth = 0
        self._in_title = False
        self._in_jsonld = False
        self.containers: dict[int, str] = {}  # id → tag for article/main/div/section

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and a.get("content"):
                self.meta.setdefault(key, a["content"].strip())
            return
        if tag == "time" and a.get("datetime"):
            self.times.append(a["datetime"])
        if tag in _VOID:
            if tag == "br" and self._cur is not None:
                self._cur.append(" ")
            return
        if tag == "title" and not self._stack_has("svg"):
            self._in_title = True
        if tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self._in_jsonld = True
            self.jsonld.append("")
        self._ids += 1
        hint = f"{a.get('class') or ''} {a.get('id') or ''} {a.get('role') or ''}"
        noisy = tag in _SKIP or bool(_NOISE.search(hint)) or a.get("aria-hidden") == "true" \
            or (tag == "header" and self._stack_has("article") is False)
        self._stack.append((tag, self._ids, noisy))
        if noisy:
            self._skip += 1
        if tag in ("article", "main", "div", "section", "td", "body"):
            self.containers[self._ids] = tag
        if self._skip == 0 and tag in _BLOCKS and self._cur is None:
            self._cur, self._cur_kind, self._cur_depth = [], _BLOCKS[tag], len(self._stack)

    def _stack_has(self, tag):
        return any(t == tag for t, _, _ in self._stack)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "script":
            self._in_jsonld = False
        # Pop to the matching tag; unbalanced HTML is common.
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                if self._cur is not None and i + 1 <= self._cur_depth:
                    self._flush()
                for _, _, noisy in self._stack[i:]:
                    if noisy:
                        self._skip -= 1
                del self._stack[i:]
                break

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self._cur or [])).strip()
        if text:
            path = tuple(i for t, i, _ in self._stack[: self._cur_depth - 1] if i in self.containers)
            self.blocks.append((path, self._cur_kind, text))
        self._cur = None

    def handle_data(self, data):
        if self._in_jsonld and self.jsonld:
            self.jsonld[-1] += data
        elif self._in_title:
            self.title += data
        elif self._cur is not None and self._skip == 0:
            self._cur.append(data)


def _iso_date(value: str) -> str:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", value or "")
    return m.group(0) if m else ""


_MONTHS = {m: i for i, m in enumerate(
    "january february march april may june july august september october november december".split(), 1)}


def _date_in_text(text: str) -> str:
    """"November 24, 2026" or "24 November 2026" → ISO date."""
    m = re.search(r"\b([A-Z][a-z]{2,8})\.? (\d{1,2}),? (\d{4})\b", text) or None
    if m and (m.group(1).lower() in _MONTHS or m.group(1).lower()[:3] in {k[:3] for k in _MONTHS}):
        month = next(i for k, i in _MONTHS.items() if k.startswith(m.group(1).lower()[:3]))
        return f"{m.group(3)}-{month:02d}-{int(m.group(2)):02d}"
    m = re.search(r"\b(\d{1,2}) ([A-Z][a-z]{2,8})\.? (\d{4})\b", text)
    if m and m.group(2).lower()[:3] in {k[:3] for k in _MONTHS}:
        month = next(i for k, i in _MONTHS.items() if k.startswith(m.group(2).lower()[:3]))
        return f"{m.group(3)}-{month:02d}-{int(m.group(1)):02d}"
    return ""


def _from_jsonld(chunks: list[str]) -> dict:
    out: dict[str, str] = {}

    def walk(node):
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            kind = node.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]
            if any(k in ("Article", "NewsArticle", "BlogPosting", "Report", "TechArticle") for k in kinds):
                out.setdefault("title", str(node.get("headline") or ""))
                out.setdefault("published", _iso_date(str(node.get("datePublished") or "")))
                author = node.get("author")
                author = author[0] if isinstance(author, list) and author else author
                name = author.get("name") if isinstance(author, dict) else author
                if isinstance(name, str):
                    out.setdefault("author", name)
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v)

    for chunk in chunks:
        try:
            walk(json.loads(chunk))
        except ValueError:
            continue
    return out


def _clean_title(title: str, site: str) -> str:
    title = re.sub(r"\s+", " ", title or "").strip()
    # "Headline | Site" / "Headline - Site": keep the headline.
    for sep in (" | ", " — ", " – ", " - ", " · "):
        if sep in title:
            head, tail = title.rsplit(sep, 1)
            if len(head) >= 12 and (not site or tail.lower().replace(" ", "") in site.lower().replace(".", "") or len(tail) <= 30):
                return head.strip()
    return title


def extract_html(html: str, url: str = "") -> Article:
    reader = _Reader()
    try:
        reader.feed(html)
        reader.close()
    except Exception:  # noqa: BLE001 - a broken page should still yield what was read
        pass
    if reader._cur is not None:
        reader._flush()

    # The article is the container holding the most paragraph text. Prefer an
    # <article>/<main> when one carries most of it.
    weight: dict[int, int] = {}
    for path, kind, text in reader.blocks:
        if kind in ("paragraph", "quote") and len(text) > 40:
            for cid in path:
                weight[cid] = weight.get(cid, 0) + len(text)
    total = max(weight.values(), default=0)
    best = None
    if total:
        deep = [cid for cid, w in weight.items() if w >= total * 0.6]
        semantic = [c for c in deep if reader.containers.get(c) in ("article", "main")]
        # Among containers holding most of the text, the innermost (highest id
        # that still qualifies) carries the least page furniture.
        best = max(semantic or deep)
    blocks = [Block(kind, text) for path, kind, text in reader.blocks if best is None or best in path]

    host = (urlparse(url).hostname or "").removeprefix("www.")
    site = reader.meta.get("og:site_name") or host
    ld = _from_jsonld(reader.jsonld)
    first_heading = next((b.text for b in blocks if b.kind == "heading"), "")
    title = ld.get("title") or reader.meta.get("og:title") or first_heading or _clean_title(reader.title, site)
    title = _clean_title(title, site)
    author = ld.get("author") or reader.meta.get("author") or reader.meta.get("article:author") or ""
    if author.startswith("http"):
        author = ""
    published = (
        ld.get("published")
        or _iso_date(reader.meta.get("article:published_time", ""))
        or _iso_date(reader.meta.get("datepublished", ""))
        or _iso_date(reader.meta.get("date", ""))
        or next((d for d in map(_iso_date, reader.times) if d), "")
    )
    art = Article(title=title, author=author.strip(), published=published, site=site, url=url, via="fetch", blocks=blocks)
    return _tidy(art)


# --- Extraction from markdown (the scrape service's output) -----------------


def extract_markdown(md: str, url: str = "", meta: dict | None = None) -> Article:
    meta = meta or {}
    blocks: list[Block] = []
    para: list[str] = []

    def strip(s: str) -> str:
        s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)  # images
        s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)  # links → their text
        s = re.sub(r"[*_`]{1,3}([^*_`]+)[*_`]{1,3}", r"\1", s)  # emphasis, code
        return re.sub(r"\s+", " ", s).strip()

    def flush(kind="paragraph"):
        text = strip(" ".join(para))
        para.clear()
        if text:
            blocks.append(Block(kind, text))

    lines = md.replace("\r\n", "\n").split("\n")
    i = 0
    in_code = False
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if line.strip().startswith("```"):
            in_code = not in_code
            flush()
        elif in_code:
            pass
        elif re.match(r"^\s*#{1,4}\s+\S", line):
            flush()
            blocks.append(Block("heading", strip(re.sub(r"^\s*#+\s+", "", line))))
        elif line.strip() and re.match(r"^\s*(=+|-{3,})\s*$", nxt) and not para:
            blocks.append(Block("heading", strip(line)))  # setext heading
            i += 1
        elif re.match(r"^\s*([-*+]|\d+[.)])\s+\S", line):
            flush()
            blocks.append(Block("item", strip(re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", line))))
        elif line.lstrip().startswith(">"):
            flush()
            blocks.append(Block("quote", strip(line.lstrip()[1:])))
        elif not line.strip() or re.match(r"^\s*([-*_]\s*){3,}$", line) or line.lstrip().startswith("|"):
            flush()
        else:
            para.append(line)
        i += 1
    flush()

    host = (urlparse(url).hostname or "").removeprefix("www.")
    site = str(meta.get("ogSiteName") or meta.get("og:site_name") or host)
    first_heading = next((b.text for b in blocks if b.kind == "heading"), "")
    title = _clean_title(str(meta.get("ogTitle") or meta.get("title") or first_heading), site)
    art = Article(
        title=title, author=str(meta.get("author") or ""),
        published=_iso_date(str(meta.get("publishedTime") or meta.get("article:published_time") or "")),
        site=site, url=url, via="scrape", blocks=blocks,
    )
    return _tidy(art)


# --- Shared clean-up --------------------------------------------------------

_BYLINE = re.compile(r"^(?:by\s+)?(?P<name>[A-Z][\w.'-]+(?: [A-Z][\w.'-]+){1,3})\s*[·•|—–-]\s*(?P<rest>.+)$")
_FURNITURE = re.compile(
    r"^(share|subscribe|sign up|sign in|log in|follow( me| us)?|back to|read more|related|comments?|"
    r"previous|next|table of contents|menu|home|essays|blog|posts?|\d+ min read)\b", re.I)


def _tidy(art: Article) -> Article:
    """Drop page furniture, lift a byline line into author/date, and remove a
    repeat of the title from the top of the text."""
    out: list[Block] = []
    for n, b in enumerate(art.blocks):
        text = b.text.strip()
        if not text:
            continue
        early = n < 8
        m = _BYLINE.match(text) if early and len(text) < 120 else None
        if m:
            art.author = art.author or m.group("name")
            art.published = art.published or _date_in_text(m.group("rest"))
            continue
        if early and len(text) < 60 and (_FURNITURE.match(text) or text.lower() == (art.site or "").lower()):
            continue
        if early and art.title and _same(text, art.title):
            continue
        out.append(Block(b.kind, text))
    # Trailing furniture: short lines after the last real paragraph.
    while out and len(out[-1].text) < 60 and _FURNITURE.match(out[-1].text):
        out.pop()
    art.blocks = out
    if not art.published:
        art.published = next((d for d in (_date_in_text(b.text) for b in art.blocks[:3] if len(b.text) < 80) if d), "")
    return art


def _same(a: str, b: str) -> bool:
    norm = lambda s: re.sub(r"[^a-z0-9]+", "", s.lower())  # noqa: E731
    return norm(a) == norm(b)


# --- Entry points -----------------------------------------------------------


def article_from_text(text: str, title: str = "") -> Article:
    """Pasted text: paragraphs are separated by blank lines; a first short
    line with no full stop is taken as the title when none was given."""
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text.replace("\r\n", "\n"))]
    paras = [p for p in paras if p]
    if not paras:
        raise ArticleError("There is no text to narrate.")
    if not title and len(paras) > 1 and len(paras[0]) <= 120 and not paras[0].rstrip().endswith((".", "!", "?", ":")):
        title, paras = paras[0], paras[1:]
    blocks = []
    for p in paras:
        if p.startswith("#"):
            blocks.append(Block("heading", p.lstrip("# ").strip()))
        else:
            blocks.append(Block("paragraph", p))
    return Article(title=title, via="text", blocks=blocks)


def read_article(url: str, scrape=None) -> Article:
    """``url`` → Article. ``scrape`` is an optional callable
    ``(url) -> (markdown, metadata) | None`` backed by the club's scrape
    service; when it returns nothing usable the page is fetched directly."""
    source = url.strip()
    if not re.match(r"^https?://", source, re.I):
        source = "https://" + source
    target, hn_title = _resolve_hacker_news(source)
    if not target:
        raise ArticleError("That Hacker News post has no outside link to read.")

    art: Article | None = None
    if scrape is not None:
        try:
            got = scrape(target)
        except Exception:  # noqa: BLE001 - the scrape service is optional
            got = None
        if got and got[0] and len(got[0].split()) >= 80:
            art = extract_markdown(got[0], target, got[1] or {})
    if art is None or art.words < 80:
        final, html = _fetch(target)
        fetched = extract_html(html, final)
        if art is None or fetched.words > art.words:
            art = fetched
    if art.words < 40:
        raise ArticleError("No article text was found on that page.")
    art.source_url = source
    if not art.title:
        art.title = hn_title
    return art
