"""
lib/seo.py
SEOメタタグと構造化データ(JSON-LD)を生成する。
- OGP / Twitter Card
- JSON-LD: BlogPosting / WebSite / BreadcrumbList / ItemList
"""

import json
import html
from lib.area import resolve_area_for_article
from lib.content import generate_meta_description, generate_meta_keywords, clean_content, count_content_chars


SITE_URL = "https://menesthe-ashitaka.com"
SITE_NAME = "メンエス好きのアシタカマガジン"
AUTHOR_NAME = "メンエス厳選情報のアシタカ"
TWITTER_HANDLE = "@sprcialize"


# ============================================================
# メタタグ（全ページ共通ヘルパー）
# ============================================================

def generate_head_meta(
    title,
    description,
    url,
    page_type="website",  # "website" | "article"
    image=None,
    keywords=None,
    article_date=None,
    article_section=None,
    noindex=False,
):
    """
    <head>内に挿入するメタタグ群を生成する。
    既存テンプレートのtitle/description/og:*を置き換える前提で、
    このモジュールが「唯一のメタタグ生成元」になる。
    """
    title_full = title if SITE_NAME in title else f"{title} | {SITE_NAME}"
    canonical = url if url.startswith("http") else f"{SITE_URL}{url}"

    lines = [
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f'<title>{html.escape(title_full)}</title>',
        f'<meta name="description" content="{html.escape(description)}">',
    ]

    if keywords:
        lines.append(f'<meta name="keywords" content="{html.escape(keywords)}">')

    # robots
    if noindex:
        lines.append('<meta name="robots" content="noindex, nofollow">')
    else:
        lines.append('<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">')

    lines.append(f'<link rel="canonical" href="{canonical}">')

    # OGP
    lines.extend([
        f'<meta property="og:type" content="{page_type}">',
        f'<meta property="og:title" content="{html.escape(title)}">',
        f'<meta property="og:description" content="{html.escape(description)}">',
        f'<meta property="og:url" content="{canonical}">',
        f'<meta property="og:site_name" content="{html.escape(SITE_NAME)}">',
        '<meta property="og:locale" content="ja_JP">',
    ])
    if image:
        lines.append(f'<meta property="og:image" content="{html.escape(image)}">')
        lines.append('<meta property="og:image:width" content="1200">')
        lines.append('<meta property="og:image:height" content="630">')

    # Twitter Card
    lines.extend([
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:site" content="{TWITTER_HANDLE}">',
        f'<meta name="twitter:creator" content="{TWITTER_HANDLE}">',
        f'<meta name="twitter:title" content="{html.escape(title)}">',
        f'<meta name="twitter:description" content="{html.escape(description)}">',
    ])
    if image:
        lines.append(f'<meta name="twitter:image" content="{html.escape(image)}">')

    # Article専用
    if page_type == "article":
        if article_date:
            lines.append(f'<meta property="article:published_time" content="{article_date}">')
            lines.append(f'<meta property="article:modified_time" content="{article_date}">')
        lines.append(f'<meta property="article:author" content="{html.escape(AUTHOR_NAME)}">')
        if article_section:
            lines.append(f'<meta property="article:section" content="{html.escape(article_section)}">')

    return "\n  ".join(lines)


# ============================================================
# 構造化データ（JSON-LD）
# ============================================================

def generate_website_jsonld():
    """サイト全体のWebSiteスキーマ（トップページに埋め込む）"""
    data = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "alternateName": "アシタカマガジン",
        "url": f"{SITE_URL}/",
        "description": "メンズエステの体験レポートと厳選情報。東京・神奈川・千葉・埼玉を中心に、アシタカが実体験をもとにレビューを公開。",
        "inLanguage": "ja",
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "url": f"{SITE_URL}/",
        },
    }
    return _jsonld_tag(data)


def generate_blogposting_jsonld(article):
    """記事ページのBlogPostingスキーマ"""
    slug = article.get("slug", "")
    url = f"{SITE_URL}/articles/{slug}/"
    title = article.get("title", "")
    description = generate_meta_description(article)
    date = article.get("date", "")

    info = resolve_area_for_article(article)
    section = info["name"] if info else article.get("area", "")

    cleaned_content = clean_content(article.get("content", ""), title)
    word_count = count_content_chars(cleaned_content)

    data = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": title,
        "description": description,
        "url": url,
        "datePublished": date,
        "dateModified": date,
        "inLanguage": "ja",
        "author": {
            "@type": "Person",
            "name": AUTHOR_NAME,
            "url": f"{SITE_URL}/about/",
        },
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "url": f"{SITE_URL}/",
        },
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": url,
        },
        "articleSection": section,
        "wordCount": word_count,
    }

    if article.get("thumbnail"):
        data["image"] = {
            "@type": "ImageObject",
            "url": article["thumbnail"],
        }

    return _jsonld_tag(data)


def generate_breadcrumb_jsonld(items):
    """
    BreadcrumbListを生成する。
    items: [{"name": "ホーム", "url": "/"}, {"name": "東京都", "url": "/areas/tokyo/"}, ...]
    最後の要素はurlがなくてもOK（現在地）
    """
    element_list = []
    for i, item in enumerate(items, start=1):
        element = {
            "@type": "ListItem",
            "position": i,
            "name": item["name"],
        }
        if item.get("url"):
            url = item["url"]
            if not url.startswith("http"):
                url = f"{SITE_URL}{url}"
            element["item"] = url
        element_list.append(element)

    data = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": element_list,
    }
    return _jsonld_tag(data)


def generate_itemlist_jsonld(articles, name, url):
    """
    記事一覧ページやエリアページ用のItemListスキーマ。
    """
    items = []
    for i, article in enumerate(articles, start=1):
        slug = article.get("slug", "")
        items.append({
            "@type": "ListItem",
            "position": i,
            "url": f"{SITE_URL}/articles/{slug}/",
            "name": article.get("title", ""),
        })

    full_url = url if url.startswith("http") else f"{SITE_URL}{url}"
    data = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": name,
        "numberOfItems": len(items),
        "url": full_url,
        "itemListElement": items,
    }
    return _jsonld_tag(data)


def generate_collectionpage_jsonld(name, description, url, about_area=None):
    """
    エリアページ用のCollectionPageスキーマ。
    """
    full_url = url if url.startswith("http") else f"{SITE_URL}{url}"
    data = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": name,
        "description": description,
        "url": full_url,
        "inLanguage": "ja",
        "isPartOf": {
            "@type": "WebSite",
            "name": SITE_NAME,
            "url": f"{SITE_URL}/",
        },
    }
    if about_area:
        data["about"] = {
            "@type": "Place",
            "name": about_area,
        }
    return _jsonld_tag(data)


# ============================================================
# 内部ヘルパー
# ============================================================

def _jsonld_tag(data):
    """dictをJSON-LD scriptタグとして出力。"""
    json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    return f'<script type="application/ld+json">{json_str}</script>'


# ============================================================
# パンくずリストのHTML生成（SEO＋UI）
# ============================================================

def generate_breadcrumb_html(items):
    """
    視覚的なパンくずリストHTMLを生成する。
    items: [{"name": "ホーム", "url": "/"}, ...]
    """
    parts = []
    for i, item in enumerate(items):
        name = html.escape(item["name"])
        url = item.get("url")
        if url and i < len(items) - 1:
            parts.append(f'<a href="{url}">{name}</a>')
        else:
            parts.append(f'<span>{name}</span>')

    return '<nav class="breadcrumb" aria-label="パンくずリスト">' + ' / '.join(parts) + '</nav>'
