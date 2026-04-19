"""
lib/sitemap.py
sitemap.xmlをSEOベストプラクティスに沿って拡張生成する。
- 画像サイトマップ対応（<image:image>）
- ページ種別ごとに最適なpriority/changefreqを設定
"""

from datetime import datetime
import html


SITE_URL = "https://menesthe-ashitaka.com"


def _xml_escape(s):
    return html.escape(s, quote=True) if s else ""


def build_sitemap(articles, shops, area_groups, free_article=None):
    """
    v3のbuild_sitemap相当だが、大幅に拡張。

    articles: 記事のリスト
    shops: 店舗のリスト
    area_groups: lib.area.group_articles_by_area() の戻り値
    free_article: 無料公開中の記事（高優先度）
    """
    now = datetime.now().strftime("%Y-%m-%d")
    urls = []

    # --- トップページ ---
    urls.append(_url_entry(
        loc=f"{SITE_URL}/",
        lastmod=now,
        changefreq="daily",
        priority="1.0",
    ))

    # --- 記事一覧 ---
    urls.append(_url_entry(
        loc=f"{SITE_URL}/articles/",
        lastmod=now,
        changefreq="daily",
        priority="0.9",
    ))

    # --- エリア一覧トップ ---
    urls.append(_url_entry(
        loc=f"{SITE_URL}/areas/",
        lastmod=now,
        changefreq="weekly",
        priority="0.9",
    ))

    # --- 各エリアページ（SEO最重要） ---
    for slug, group in area_groups.items():
        info = group["info"]
        if not info:
            continue
        # 駅レベルのページを最優先、都道府県フォールバックは中優先
        priority = "0.9" if info.get("is_station") else "0.7"
        urls.append(_url_entry(
            loc=f"{SITE_URL}/areas/{slug}/",
            lastmod=now,
            changefreq="weekly",
            priority=priority,
        ))

    # --- 固定ページ ---
    urls.append(_url_entry(
        loc=f"{SITE_URL}/shops/",
        lastmod=now,
        changefreq="weekly",
        priority="0.7",
    ))
    urls.append(_url_entry(
        loc=f"{SITE_URL}/about/",
        lastmod=now,
        changefreq="monthly",
        priority="0.5",
    ))

    # --- 無料公開記事（全文公開なのでSEO価値最高） ---
    free_slug = None
    if free_article and free_article.get("slug"):
        free_slug = free_article["slug"]
        urls.append(_url_entry(
            loc=f"{SITE_URL}/articles/{free_slug}/",
            lastmod=free_article.get("date", now),
            changefreq="weekly",
            priority="0.9",
            image_url=free_article.get("thumbnail"),
            image_title=free_article.get("title"),
        ))

    # --- 個別記事 ---
    for article in articles:
        slug = article.get("slug", "")
        if slug == free_slug:
            continue  # 無料記事は上で出力済み

        title = article.get("title", "")
        is_closed = any(marker in title for marker in ("閉店", "退店済み", "販売停止"))

        priority = "0.5" if is_closed else "0.7"

        urls.append(_url_entry(
            loc=f"{SITE_URL}/articles/{slug}/",
            lastmod=article.get("date", now),
            changefreq="monthly",
            priority=priority,
            image_url=article.get("thumbnail"),
            image_title=title,
        ))

    # --- 店舗ページ ---
    for shop in shops:
        slug = shop.get("slug", "")
        if not slug:
            continue
        urls.append(_url_entry(
            loc=f"{SITE_URL}/shops/{slug}/",
            lastmod=now,
            changefreq="monthly",
            priority="0.5",
        ))

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
    xml += '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'
    xml += "\n".join(urls)
    xml += '\n</urlset>\n'

    return xml, len(urls)


def _url_entry(loc, lastmod, changefreq, priority, image_url=None, image_title=None):
    """個別の<url>エントリを生成。"""
    parts = [
        f"  <url>",
        f"    <loc>{_xml_escape(loc)}</loc>",
        f"    <lastmod>{lastmod}</lastmod>",
        f"    <changefreq>{changefreq}</changefreq>",
        f"    <priority>{priority}</priority>",
    ]
    if image_url:
        parts.append(f"    <image:image>")
        parts.append(f"      <image:loc>{_xml_escape(image_url)}</image:loc>")
        if image_title:
            # 長すぎるタイトルは切る
            title = image_title[:100]
            parts.append(f"      <image:title>{_xml_escape(title)}</image:title>")
        parts.append(f"    </image:image>")
    parts.append("  </url>")
    return "\n".join(parts)
