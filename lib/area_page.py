"""
lib/area_page.py
駅・エリア別のまとめページを生成する。
- /areas/{slug}/         各駅のまとめページ
- /areas/                エリア一覧トップ
"""

import os
import html
from lib.area import (
    group_articles_by_area, group_by_parent_area,
    resolve_area_for_article, extract_genres,
    PARENT_AREA_MASTER, GENRE_PATTERNS,
)
from lib.seo import (
    generate_head_meta, generate_breadcrumb_jsonld,
    generate_itemlist_jsonld, generate_collectionpage_jsonld,
    generate_breadcrumb_html, SITE_URL, SITE_NAME,
)


# ============================================================
# エリア紹介文の自動生成
# ============================================================

def _generate_area_intro(area_info, articles):
    """エリアページの導入文を記事データから自動生成する。"""
    name = area_info["name"]
    count = len(articles)
    parent_key = area_info["parent"]
    parent_label = PARENT_AREA_MASTER.get(parent_key, ("", ""))[0]

    # 系統別集計
    genre_counts = {}
    for a in articles:
        for g in extract_genres(a):
            genre_counts[g] = genre_counts.get(g, 0) + 1

    # 最も多い系統トップ3
    top_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    genre_summary = "、".join(
        f"{GENRE_PATTERNS[g][1]}系{cnt}本" for g, cnt in top_genres if g in GENRE_PATTERNS
    )

    # 最新記事と最古記事
    sorted_articles = sorted(articles, key=lambda a: a.get("date", ""))
    oldest = sorted_articles[0].get("date", "") if sorted_articles else ""
    newest = sorted_articles[-1].get("date", "") if sorted_articles else ""

    intro_parts = []
    intro_parts.append(
        f'<p>{html.escape(name)}エリアは{parent_label}の中でも、'
        f'メンエス好きのアシタカが重点的にレポートしているエリアです。'
        f'このページでは、アシタカが実際に体験した{count}本のレポートを'
        f'一覧でご覧いただけます。</p>'
    )

    if genre_summary:
        intro_parts.append(
            f'<p>{html.escape(name)}で取り扱っているレポートの系統は、'
            f'{html.escape(genre_summary)}などが中心。'
            f'系統別フィルターで絞り込めるので、お好みの傾向から探してみてください。</p>'
        )

    if oldest and newest:
        intro_parts.append(
            f'<p class="area-meta" style="font-size:13px; color:#666;">'
            f'掲載レポート期間: {oldest} 〜 {newest} ・ 全{count}本</p>'
        )

    return "\n".join(intro_parts)


# ============================================================
# 記事カード生成（エリアページ用・系統タグ付き）
# ============================================================

def _generate_article_card_with_genres(article):
    """エリアページ用の記事カード。data-genres属性で系統フィルター対応。"""
    thumb = article.get("thumbnail", "")
    title_escaped = html.escape(article.get("title", ""))
    slug = article.get("slug", "")
    date = article.get("date", "")

    info = resolve_area_for_article(article)
    area_name = info["name"] if info else article.get("area", "")

    thumb_html = (
        f'<img src="{html.escape(thumb)}" alt="{title_escaped}" loading="lazy">'
        if thumb else '<span class="placeholder">📝</span>'
    )

    genres = extract_genres(article)
    genres_attr = " ".join(genres)

    excerpt = article.get("excerpt", "")
    # エクセルプトがナビゲーションゴミなら空に
    from lib.content import _is_navigation_noise
    if _is_navigation_noise(excerpt, article.get("title", "")):
        excerpt = ""

    excerpt_escaped = html.escape(excerpt[:80])

    return f'''
    <a href="/articles/{slug}/" class="article-card" data-genres="{genres_attr}">
      <div class="article-thumb">{thumb_html}</div>
      <div class="article-body">
        <div class="article-meta">{html.escape(area_name)} ・ {date}</div>
        <h3 class="article-title">{title_escaped}</h3>
        <p class="article-excerpt">{excerpt_escaped}</p>
        <span class="article-read-more">続きを読む →</span>
      </div>
    </a>'''


def _generate_genre_filter_buttons(articles):
    """系統別フィルターボタンを生成。そのエリアに存在する系統のみ表示。"""
    genre_counts = {}
    for a in articles:
        for g in extract_genres(a):
            genre_counts[g] = genre_counts.get(g, 0) + 1

    if not genre_counts:
        return ""

    # 件数降順
    sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)

    buttons = []
    for genre_key, count in sorted_genres:
        if genre_key not in GENRE_PATTERNS:
            continue
        _patterns, label = GENRE_PATTERNS[genre_key]
        buttons.append(
            f'<button class="filter-btn" data-filter="{genre_key}">'
            f'{html.escape(label)}（{count}）</button>'
        )
    return "\n        ".join(buttons)


def _generate_other_areas_nav(current_slug, all_area_groups):
    """他エリアへのナビゲーションHTMLを生成。"""
    by_parent = {}
    for slug, group in all_area_groups.items():
        if slug == current_slug:
            continue
        info = group["info"]
        if not info or not info.get("is_station"):
            continue
        by_parent.setdefault(info["parent"], []).append({
            "slug": slug,
            "name": info["name"],
            "count": len(group["articles"]),
        })

    parent_order = ["tokyo", "kanagawa", "tama", "saitama", "chiba"]
    sections = []
    for parent in parent_order:
        if parent not in by_parent:
            continue
        areas = sorted(by_parent[parent], key=lambda x: x["count"], reverse=True)
        if not areas:
            continue
        parent_label = PARENT_AREA_MASTER[parent][0]
        links = " ・ ".join(
            f'<a href="/areas/{a["slug"]}/">{html.escape(a["name"])}（{a["count"]}）</a>'
            for a in areas
        )
        sections.append(f'<p><strong>{parent_label}：</strong>{links}</p>')

    return "\n      ".join(sections)


# ============================================================
# 個別エリアページ生成
# ============================================================

def build_area_page(area_slug, area_group, all_area_groups, template, public_dir, ga4_tag=""):
    """
    1つのエリアページを生成する。

    Parameters:
        area_slug: エリアのslug
        area_group: {"info": {...}, "articles": [...]}
        all_area_groups: 全エリアのgroups（他エリア誘導に使用）
        template: エリアテンプレート文字列
        public_dir: 出力先ディレクトリ
        ga4_tag: GA4タグHTML
    """
    info = area_group["info"]
    articles = area_group["articles"]
    if not info or not articles:
        return False

    name = info["name"]
    count = len(articles)
    url = f"/areas/{area_slug}/"

    # --- メタ情報 ---
    page_title = f"{name}のメンエス厳選レポート{count}件"
    description = (
        f"{name}のメンズエステ体験レポート{count}本を掲載。"
        f"アシタカが実際に体験したレビューを、系統別（爆乳・スレンダー・人妻・ロリなど）"
        f"で絞り込み可能。{name}でメンエスを探すならまずここ。"
    )[:155]

    keywords = ",".join(info["keywords"] + ["メンエス", "メンズエステ", "体験談", "口コミ", "レビュー"])

    # 代表画像は最新記事のサムネイルを使用
    representative_image = None
    for a in articles:
        if a.get("thumbnail"):
            representative_image = a["thumbnail"]
            break

    head_meta = generate_head_meta(
        title=page_title,
        description=description,
        url=url,
        page_type="website",
        image=representative_image,
        keywords=keywords,
    )

    # --- 構造化データ ---
    breadcrumb_items = [
        {"name": "ホーム", "url": "/"},
        {"name": "エリア一覧", "url": "/areas/"},
        {"name": name},
    ]
    jsonld_parts = [
        generate_collectionpage_jsonld(
            name=page_title,
            description=description,
            url=url,
            about_area=name,
        ),
        generate_breadcrumb_jsonld(breadcrumb_items),
        generate_itemlist_jsonld(articles, page_title, url),
    ]
    jsonld = "\n  ".join(jsonld_parts)

    # --- ボディ ---
    breadcrumb_html = generate_breadcrumb_html(breadcrumb_items)
    area_intro = _generate_area_intro(info, articles)
    genre_buttons = _generate_genre_filter_buttons(articles)
    article_cards = "\n".join(_generate_article_card_with_genres(a) for a in articles)
    other_areas_nav = _generate_other_areas_nav(area_slug, all_area_groups)

    # --- テンプレート置換 ---
    html_out = template
    replacements = {
        "{{HEAD_META}}":           head_meta,
        "{{JSON_LD}}":             jsonld,
        "{{GA4_TAG}}":             ga4_tag,
        "{{BREADCRUMB_HTML}}":     breadcrumb_html,
        "{{AREA_NAME}}":           html.escape(name),
        "{{COUNT}}":               str(count),
        "{{AREA_INTRO}}":          area_intro,
        "{{GENRE_FILTER_BUTTONS}}": genre_buttons,
        "{{ARTICLE_CARDS}}":       article_cards,
        "{{OTHER_AREAS_NAV}}":     other_areas_nav,
    }
    for k, v in replacements.items():
        html_out = html_out.replace(k, v)

    # --- 書き出し ---
    output_dir = os.path.join(public_dir, "areas", area_slug)
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_out)

    return True


# ============================================================
# エリア一覧トップページ生成
# ============================================================

def build_area_index_page(area_groups, public_dir, ga4_tag=""):
    """/areas/ のエリア一覧ページを生成。"""

    # 親エリア別にグルーピング
    by_parent = group_by_parent_area(area_groups)

    page_title = "エリア一覧 | 全エリアのメンエス体験レポート"
    total_count = sum(len(g["articles"]) for g in area_groups.values())
    description = (
        f"メンエス好きのアシタカが体験した{total_count}本以上のレポートを"
        f"エリア別に整理。東京・神奈川・千葉・埼玉の主要駅ごとに"
        f"絞り込んで探せます。"
    )[:155]

    head_meta = generate_head_meta(
        title=page_title,
        description=description,
        url="/areas/",
        page_type="website",
        keywords="メンエス,メンズエステ,エリア,東京,神奈川,千葉,埼玉",
    )

    breadcrumb_items = [
        {"name": "ホーム", "url": "/"},
        {"name": "エリア一覧"},
    ]
    jsonld_parts = [
        generate_breadcrumb_jsonld(breadcrumb_items),
    ]
    jsonld = "\n  ".join(jsonld_parts)
    breadcrumb_html = generate_breadcrumb_html(breadcrumb_items)

    # 親エリアごとに駅リストを展開
    parent_order = ["tokyo", "kanagawa", "tama", "saitama", "chiba", "nouhau"]
    sections_html = []
    for parent in parent_order:
        if parent not in by_parent:
            continue
        areas = sorted(
            [a for a in by_parent[parent] if a.get("is_station")],
            key=lambda x: x["count"], reverse=True
        )
        fallback_areas = [a for a in by_parent[parent] if not a.get("is_station")]

        if not areas and not fallback_areas:
            continue

        parent_label = PARENT_AREA_MASTER[parent][0]
        section_html = f'<section class="parent-area-section"><h2>{html.escape(parent_label)}</h2>'
        section_html += '<div class="area-grid">'
        for a in areas:
            section_html += (
                f'<a href="/areas/{a["slug"]}/" class="area-link-card">'
                f'<strong>{html.escape(a["name"])}</strong>'
                f'<span>{a["count"]}件のレポート</span>'
                f'</a>'
            )
        for a in fallback_areas:
            section_html += (
                f'<a href="/areas/{a["slug"]}/" class="area-link-card">'
                f'<strong>{html.escape(a["name"])}</strong>'
                f'<span>{a["count"]}件</span>'
                f'</a>'
            )
        section_html += '</div></section>'
        sections_html.append(section_html)

    body_html = f'''<!DOCTYPE html>
<html lang="ja">
<head>
  {head_meta}
  <link rel="stylesheet" href="/css/style.css">
  {jsonld}
  {ga4_tag}
  <style>
    .parent-area-section {{ margin-bottom: 32px; }}
    .parent-area-section h2 {{ font-size: 18px; padding-bottom: 8px; border-bottom: 2px solid var(--primary, #3B82F6); margin-bottom: 16px; }}
    .area-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }}
    .area-link-card {{ display: flex; flex-direction: column; padding: 14px 16px; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; text-decoration: none; color: inherit; transition: all .15s; }}
    .area-link-card:hover {{ border-color: var(--primary, #3B82F6); transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,.05); }}
    .area-link-card strong {{ font-size: 16px; margin-bottom: 4px; }}
    .area-link-card span {{ font-size: 12px; color: #666; }}
  </style>
</head>
<body>
  <header class="site-header">
    <div class="header-inner">
      <a href="/" class="site-logo">
        メンエス好きのアシタカマガジン
        <small>by ワクスト</small>
      </a>
      <button class="mobile-menu-btn" onclick="document.getElementById('siteNav').classList.toggle('open')" aria-label="メニュー">☰</button>
      <nav>
        <ul class="site-nav" id="siteNav">
          <li><a href="/">ホーム</a></li>
          <li><a href="/articles/">記事一覧</a></li>
          <li><a href="/areas/" class="active">エリア</a></li>
          <li><a href="/shops/">店舗紹介</a></li>
          <li><a href="/about/">About</a></li>
        </ul>
      </nav>
    </div>
  </header>
  <main class="container">
    {breadcrumb_html}
    <section>
      <h1>エリアで探す</h1>
      <p style="color:#555;">アシタカの体験レポート{total_count}本を、東京・神奈川・千葉・埼玉の主要駅ごとに整理。気になる駅名をタップしてください。</p>
    </section>
    {"".join(sections_html)}
  </main>
  <footer class="site-footer">
    <ul class="footer-links">
      <li><a href="/">ホーム</a></li>
      <li><a href="/articles/">記事一覧</a></li>
      <li><a href="/areas/">エリア一覧</a></li>
      <li><a href="/shops/">店舗紹介</a></li>
      <li><a href="/about/">About</a></li>
      <li><a href="https://wakust.com/" target="_blank" rel="noopener">ワクスト</a></li>
    </ul>
    <p class="footer-copy">&copy; 2026 メンエス好きのアシタカマガジン ・ Powered by ワクスト</p>
  </footer>
</body>
</html>'''

    output_dir = os.path.join(public_dir, "areas")
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(body_html)

    return True
