#!/usr/bin/env python3
"""
ビルドスクリプト v4

v3からの主な改善点:
- SEOメタタグの完全実装（description / keywords / OGP / Twitter Card / canonical）
- 構造化データ（JSON-LD）の大幅拡張（BlogPosting + BreadcrumbList + ItemList + WebSite）
- エリア別まとめページ自動生成（/areas/{slug}/ 形式）
- エリア一覧トップページ（/areas/）
- 記事本文のナビゲーションゴミ除去
- 関連記事・エリアナビによる内部リンク強化
- 画像サイトマップ対応のsitemap.xml
- パンくずリスト（SEO + UI）
- Google Analytics 4 (GA4) 対応

既存の機能（v3から継承）:
- articles.json / shops.json / sale_articles.json / bestseller_articles.json / free_article.json
- 今週のセール記事セクション
- カテゴリーフィルター
- 無料公開記事ページ
- 売れ筋ランキング
"""

import json
import os
import re
import shutil
import sys
from datetime import datetime

# libを import path に追加
SITE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SITE_DIR)

from lib.area import (
    group_articles_by_area, resolve_area_for_article, extract_genres, area_to_filter_key_v3_compat,
)
from lib.content import (
    clean_content, generate_meta_description, generate_meta_keywords,
    generate_related_articles_block, generate_area_nav_block,
)
from lib.seo import (
    generate_head_meta, generate_website_jsonld, generate_blogposting_jsonld,
    generate_breadcrumb_jsonld, generate_itemlist_jsonld, generate_breadcrumb_html,
    SITE_URL, SITE_NAME,
)
from lib.sitemap import build_sitemap as build_sitemap_v2
from lib.area_page import build_area_page, build_area_index_page


DATA_DIR = os.path.join(SITE_DIR, "data")
TEMPLATE_DIR = os.path.join(SITE_DIR, "templates")
PUBLIC_DIR = os.path.join(SITE_DIR, "public")


# ============================================================
# 環境変数から読み込む設定
# ============================================================
GA4_ID = os.environ.get("GA4_MEASUREMENT_ID", "").strip()
GSC_VERIFICATION = os.environ.get("GSC_VERIFICATION", "").strip()


def generate_ga4_tag():
    """GA4タグHTMLを生成。環境変数が設定されていれば出力、なければ空。"""
    if not GA4_ID:
        return "<!-- GA4 not configured -->"
    return f'''<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id={GA4_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{GA4_ID}', {{ 'anonymize_ip': true }});
</script>'''


def inject_gsc_verification(head_html):
    """Search Console認証メタタグをhead_htmlに追加。"""
    if not GSC_VERIFICATION:
        return head_html
    return head_html + f'\n  <meta name="google-site-verification" content="{GSC_VERIFICATION}">'


# ============================================================
# データ読み込み
# ============================================================

def load_json(filename):
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def load_template(filename):
    filepath = os.path.join(TEMPLATE_DIR, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def escape_html(text):
    if not text:
        return ""
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))


# ============================================================
# 記事カード生成（v3互換）
# ============================================================

def generate_article_card(article, with_data_area=False):
    """記事カードHTMLを生成（v3互換）"""
    thumb = article.get("thumbnail", "")
    title_escaped = escape_html(article["title"])
    if thumb:
        thumb_html = f'<img src="{thumb}" alt="{title_escaped}" loading="lazy">'
    else:
        thumb_html = '<span class="placeholder">📝</span>'

    area = article.get("area", "")
    area_key = area_to_filter_key_v3_compat(area)
    data_attr = f' data-area="{area_key}"' if with_data_area else ""

    return f'''
    <div class="article-card"{data_attr}>
      <a href="/articles/{article["slug"]}/">
        <div class="article-thumb">{thumb_html}</div>
        <div class="article-body">
          <div class="article-meta">{escape_html(area)} ・ {article["date"]}</div>
          <h3 class="article-title">{title_escaped}</h3>
          <p class="article-excerpt">{escape_html(article.get("excerpt", ""))}</p>
          <span class="article-read-more">続きを読む →</span>
        </div>
      </a>
    </div>'''


def generate_shop_card(shop):
    tags_html = ""
    for tag in shop.get("tags", []):
        color = tag.get("color", "blue")
        tags_html += f'<span class="tag {color}">{escape_html(tag["label"])}</span>'
    return f'''
    <a href="/shops/{shop["slug"]}/" class="shop-card">
      <div class="shop-icon">{escape_html(shop["name"][0])}</div>
      <div class="shop-info">
        <h3>{escape_html(shop["name"])}</h3>
        <p class="shop-location">{escape_html(shop.get("area", ""))} ・ {escape_html(shop.get("type", ""))}</p>
        <div class="shop-tags">{tags_html}</div>
      </div>
    </a>'''


# ============================================================
# 記事ページ生成（v4 - SEO強化版）
# ============================================================

def build_article_pages(articles, template, all_articles):
    """個別記事ページを生成。v4ではSEOメタタグと関連記事ブロックが拡張される。"""
    ga4_tag = generate_ga4_tag()

    for article in articles:
        slug = article["slug"]
        title = article["title"]
        url = f"/articles/{slug}/"

        # --- SEOメタ情報 ---
        description = generate_meta_description(article)
        keywords = generate_meta_keywords(article)
        info = resolve_area_for_article(article)
        area_section = info["name"] if info else article.get("area", "")
        area_slug = info["slug"] if info else ""

        head_meta = generate_head_meta(
            title=title,
            description=description,
            url=url,
            page_type="article",
            image=article.get("thumbnail"),
            keywords=keywords,
            article_date=article.get("date"),
            article_section=area_section,
        )
        head_meta = inject_gsc_verification(head_meta)

        # --- 構造化データ ---
        breadcrumb_items = [
            {"name": "ホーム", "url": "/"},
            {"name": "エリア一覧", "url": "/areas/"},
        ]
        if info:
            breadcrumb_items.append({"name": info["name"], "url": f"/areas/{info['slug']}/"})
        breadcrumb_items.append({"name": title[:40]})

        jsonld_parts = [
            generate_blogposting_jsonld(article),
            generate_breadcrumb_jsonld(breadcrumb_items),
        ]
        jsonld = "\n  ".join(jsonld_parts)

        # --- コンテンツ ---
        cleaned_content = clean_content(article.get("content", ""), title)
        # コンテンツが薄すぎる場合はexcerptで補強
        if not cleaned_content or len(re.sub(r'<[^>]+>', '', cleaned_content)) < 30:
            excerpt = article.get("excerpt", "")
            if excerpt and excerpt.strip():
                cleaned_content = f"<p>{escape_html(excerpt)}</p>"

        breadcrumb_html = generate_breadcrumb_html(breadcrumb_items)
        related_html = generate_related_articles_block(article, all_articles, limit=6)
        area_nav_html = generate_area_nav_block(article, all_articles)

        # --- テンプレート置換 ---
        html = template
        replacements = {
            "{{HEAD_META}}":          head_meta,
            "{{JSON_LD}}":            jsonld,
            "{{GA4_TAG}}":            ga4_tag,
            "{{BREADCRUMB_HTML}}":    breadcrumb_html,
            "{{TITLE}}":              escape_html(title),
            "{{DATE}}":               article.get("date", ""),
            "{{AREA_SLUG}}":          area_slug if area_slug else "tokyo-other",
            "{{AREA_DISPLAY}}":       escape_html(area_section),
            "{{CONTENT}}":            cleaned_content,
            "{{WAKUST_URL}}":         article.get("wakust_url", "https://wakust.com/"),
            "{{RELATED_ARTICLES}}":   related_html,
            "{{AREA_NAV_BLOCK}}":     area_nav_html,
        }
        for k, v in replacements.items():
            html = html.replace(k, v)

        # --- 書き出し ---
        output_dir = os.path.join(PUBLIC_DIR, "articles", slug)
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)

    print(f"  記事ページ: {len(articles)}件 生成完了（SEO強化版）")


# ============================================================
# トップページ・一覧ページ（v3互換）
# ============================================================

def generate_featured_card(article, card_type="green"):
    """無料記事またはセール記事の大きめカードHTML（v3互換）"""
    thumb = article.get("thumbnail", "")
    title_escaped = escape_html(article.get("title", ""))
    thumb_html = f'<img src="{thumb}" alt="{title_escaped}" loading="lazy">' if thumb else ''

    if card_type == "green":
        badge_text = "全文無料公開中"
        badge_class = "green"
        btn_text = "この記事を無料で読む →"
        btn_class = "green"
        link = f'/articles/{article.get("slug", "")}/'
        target = ""
    else:
        badge_text = "セール中"
        badge_class = "orange"
        btn_text = "ワクストでセール記事を見る →"
        btn_class = "orange"
        link = article.get("wakust_url", "https://wakust.com/user/ryu-1992/")
        target = ' target="_blank" rel="noopener"'

    area = escape_html(article.get("area", article.get("category", "")))
    date = article.get("date", article.get("post_date", ""))

    return f'''
      <div class="featured-card {card_type}">
        <div class="featured-card-top">
          <span class="featured-badge {badge_class}">{badge_text}</span>
          <span class="featured-timer"><span class="featured-timer-icon"></span><span class="countdown-timer"></span></span>
        </div>
        <div class="featured-thumb">{thumb_html}</div>
        <div class="featured-body">
          <div class="featured-title">{title_escaped}</div>
          <div class="featured-meta">{area} ・ {date}</div>
        </div>
        <a href="{link}" class="featured-btn {btn_class}"{target}>{btn_text}</a>
      </div>'''


def generate_ranking_item(article, rank):
    thumb = article.get("thumbnail", "")
    title_escaped = escape_html(article.get("title", ""))
    thumb_html = f'<img src="{thumb}" alt="{title_escaped}" loading="lazy">' if thumb else ''
    top3_class = " top3" if rank <= 3 else ""
    num_class = f"r{rank}" if rank <= 3 else "r-other"
    link = article.get("wakust_url", f'/articles/wakust-{article.get("id", "")}/')
    return f'''
      <a href="{link}" class="ranking-item{top3_class}" target="_blank" rel="noopener">
        <div class="ranking-num {num_class}">{rank}</div>
        <div class="ranking-thumb">{thumb_html}</div>
        <div class="ranking-title">{title_escaped}</div>
      </a>'''


def build_index(articles, shops, sale_articles, bestseller_articles, free_article):
    """トップページ生成。v4ではWebSite JSON-LDを追加。"""
    index_path = os.path.join(PUBLIC_DIR, "index.html")
    if not os.path.exists(index_path):
        print(f"  警告: {index_path} が存在しません")
        return

    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    # === Featured Row (無料記事 + セール記事) ===
    has_free = free_article and free_article.get("title")
    has_sale = sale_articles and len(sale_articles) > 0

    if has_free or has_sale:
        featured_html = ""
        if has_free:
            featured_html += generate_featured_card(free_article, "green")
        if has_sale:
            featured_html += generate_featured_card(sale_articles[0], "orange")

        html = re.sub(
            r'(<div class="featured-row" id="featuredRow">)\s*(</div>)',
            rf'\1{featured_html}\2', html, flags=re.DOTALL,
        )
        html = html.replace('id="featuredSection" style="display:none;"', 'id="featuredSection"')

    # === 最新記事 ===
    if articles:
        latest = sorted(articles, key=lambda a: a["date"], reverse=True)[:3]
        cards_html = "".join(generate_article_card(a) for a in latest)
    else:
        cards_html = '<div style="text-align:center;padding:40px;color:#888;">記事を準備中です。</div>'

    html = re.sub(
        r'(<div class="articles-grid" id="latestArticles">).*?(</div>\s*</section>)',
        rf'\1{cards_html}\2', html, flags=re.DOTALL,
    )

    # === 売れ筋ランキング ===
    if bestseller_articles:
        weekly_html = "".join(generate_ranking_item(a, i + 1) for i, a in enumerate(bestseller_articles[:10]))
    else:
        weekly_html = '<div style="text-align:center;padding:30px;color:#888;">データ取得中です</div>'

    html = re.sub(
        r'(<div class="ranking-list" id="rankWeekly">)\s*(</div>)',
        rf'\1{weekly_html}\2', html, flags=re.DOTALL,
    )

    all_data = load_json("all_articles_data.json")
    if all_data:
        sorted_all = sorted(all_data, key=lambda a: a.get("sales_amount", 0), reverse=True)[:10]
        total_html = "".join(generate_ranking_item(a, i + 1) for i, a in enumerate(sorted_all))
    else:
        total_html = '<div style="text-align:center;padding:30px;color:#888;">データ取得中です</div>'

    html = re.sub(
        r'(<div class="ranking-list" id="rankTotal" style="display:none;">)\s*(</div>)',
        rf'\1{total_html}\2', html, flags=re.DOTALL,
    )

    # === SEOメタタグとJSON-LDの挿入 ===
    site_desc = "メンズエステの体験レポートと厳選情報。東京・神奈川・千葉・埼玉を中心にアシタカが実体験をもとにレビュー。秋葉原・新宿・池袋・武蔵小杉・立川など主要駅のまとめページあり。"
    head_meta = generate_head_meta(
        title="メンエス好きのアシタカマガジン | メンズエステ体験レポート",
        description=site_desc,
        url="/",
        page_type="website",
        keywords="メンエス,メンズエステ,体験談,口コミ,秋葉原,新宿,池袋,武蔵小杉,立川,アシタカ",
    )
    head_meta = inject_gsc_verification(head_meta)
    jsonld = generate_website_jsonld()
    ga4 = generate_ga4_tag()

    # 既存の<head>内の重複するタグを除去して、新しいメタタグに置換
    html = _replace_head_meta(html, head_meta, jsonld, ga4)

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("  トップページ: 更新完了（SEO強化）")


def _replace_head_meta(html, new_head_meta, jsonld, ga4_tag):
    """
    既存HTMLの<head>内にある基本メタタグを新版で置き換える。
    冪等性を保つため、既にSEO強化版が入っているかチェックする。
    """
    # 既存のtitle/description/og:*を削除
    # 複数回のビルドで重複しないように、v4生成マーカーで囲んで管理
    MARKER_START = "<!-- SEO v4 BEGIN -->"
    MARKER_END = "<!-- SEO v4 END -->"

    seo_block = f"{MARKER_START}\n  {new_head_meta}\n  {jsonld}\n  {ga4_tag}\n  {MARKER_END}"

    # 既にマーカーがあれば置換、なければ</head>の直前に挿入
    if MARKER_START in html and MARKER_END in html:
        html = re.sub(
            re.escape(MARKER_START) + r'.*?' + re.escape(MARKER_END),
            seo_block,
            html,
            flags=re.DOTALL,
        )
    else:
        html = html.replace("</head>", f"  {seo_block}\n</head>")

    return html


def build_articles_list(articles):
    list_path = os.path.join(PUBLIC_DIR, "articles", "index.html")
    if not os.path.exists(list_path):
        print(f"  警告: {list_path} が存在しません")
        return

    with open(list_path, "r", encoding="utf-8") as f:
        html = f.read()

    sorted_articles = sorted(articles, key=lambda a: a["date"], reverse=True)

    # カテゴリーフィルター生成（v3互換）
    areas_seen = {}
    for a in sorted_articles:
        area = a.get("area", "")
        if area:
            key = area_to_filter_key_v3_compat(area)
            if key not in areas_seen:
                areas_seen[key] = area

    filter_buttons = '<button class="filter-btn active" data-filter="all">すべて</button>\n'
    for key, label in areas_seen.items():
        filter_buttons += f'        <button class="filter-btn" data-filter="{key}">{escape_html(label)}</button>\n'

    html = re.sub(
        r'(<div class="shops-filter"[^>]*>).*?(</div>)',
        rf'\1\n        {filter_buttons}      \2', html, flags=re.DOTALL,
    )

    if sorted_articles:
        cards_html = "".join(generate_article_card(a, with_data_area=True) for a in sorted_articles)
    else:
        cards_html = '<div style="text-align:center;padding:40px;color:#888;">記事を準備中です。</div>'

    html = re.sub(
        r'(<div class="articles-grid" id="articlesList">).*?(</div>\s*</section>)',
        rf'\1{cards_html}\2', html, flags=re.DOTALL,
    )

    # フィルタースクリプト
    new_script = """<script>
    function toggleMenu() { document.getElementById('siteNav').classList.toggle('open'); }
    document.querySelectorAll('.filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const filter = btn.getAttribute('data-filter');
        document.querySelectorAll('#articlesList .article-card').forEach(card => {
          if (filter === 'all' || card.getAttribute('data-area') === filter) {
            card.classList.remove('hidden-by-filter');
          } else {
            card.classList.add('hidden-by-filter');
          }
        });
      });
    });
  </script>"""

    html = re.sub(r'<script>.*?</script>', new_script, html, flags=re.DOTALL)

    # SEOメタ
    head_meta = generate_head_meta(
        title="記事一覧 | メンエス好きのアシタカマガジン",
        description=f"アシタカが体験したメンズエステ体験レポート{len(articles)}本を一覧で公開。エリア・系統で絞り込み可能。東京・神奈川・千葉・埼玉の主要駅のレポートあり。",
        url="/articles/",
        page_type="website",
        keywords="メンエス,メンズエステ,記事一覧,体験談,口コミ,レビュー",
    )
    head_meta = inject_gsc_verification(head_meta)

    breadcrumb_items = [
        {"name": "ホーム", "url": "/"},
        {"name": "記事一覧"},
    ]
    jsonld_parts = [
        generate_breadcrumb_jsonld(breadcrumb_items),
        generate_itemlist_jsonld(sorted_articles[:50], "記事一覧", "/articles/"),
    ]
    jsonld = "\n  ".join(jsonld_parts)
    ga4 = generate_ga4_tag()

    html = _replace_head_meta(html, head_meta, jsonld, ga4)

    with open(list_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("  記事一覧ページ: 更新完了（SEO強化）")


def build_shops_list(shops):
    list_path = os.path.join(PUBLIC_DIR, "shops", "index.html")
    if not os.path.exists(list_path):
        return
    with open(list_path, "r", encoding="utf-8") as f:
        html = f.read()
    shops_html = "".join(generate_shop_card(s) for s in shops)
    html = re.sub(
        r'(<div class="shops-grid" id="shopsList">).*?(</div>\s*</section>)',
        rf'\1{shops_html}\2', html, flags=re.DOTALL,
    )
    with open(list_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("  店舗一覧ページ: 更新完了")


# ============================================================
# sitemap.xml / robots.txt（v4 拡張版）
# ============================================================

def build_sitemap_and_robots(articles, shops, area_groups, free_article):
    sitemap_xml, count = build_sitemap_v2(articles, shops, area_groups, free_article)
    with open(os.path.join(PUBLIC_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap_xml)
    print(f"  sitemap.xml: {count}件 生成完了")

    # robots.txt は事前に用意された最適化版を使用（リポジトリルートの robots.txt）
    robots_src = os.path.join(SITE_DIR, "robots.txt")
    robots_dst = os.path.join(PUBLIC_DIR, "robots.txt")
    if os.path.exists(robots_src):
        shutil.copy2(robots_src, robots_dst)
        print("  robots.txt: コピー完了（カスタム版）")
    else:
        # フォールバック
        with open(robots_dst, "w", encoding="utf-8") as f:
            f.write(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n")
        print("  robots.txt: 生成完了（シンプル版）")


# ============================================================
# 無料記事の全文ページ（v3互換・SEO強化）
# ============================================================

def build_free_article_page(free_article, template, all_articles):
    if not free_article or not free_article.get("title"):
        return

    slug = free_article["slug"]
    title = free_article["title"]
    output_dir = os.path.join(PUBLIC_DIR, "articles", slug)
    os.makedirs(output_dir, exist_ok=True)

    # 無料本文 + 有料本文
    free_text = free_article.get("free_content", "")
    paid_text = free_article.get("paid_content", "")

    if free_text and not free_text.strip().startswith("<"):
        free_html = "\n".join(f"<p>{p.strip()}</p>" for p in free_text.split("\n") if p.strip())
    else:
        free_html = free_text

    full_content = clean_content(free_html, title)
    if paid_text:
        full_content += '\n<hr style="margin: 2em 0; border: none; border-top: 2px dashed var(--primary);">\n'
        full_content += '<p style="text-align:center; color: var(--primary); font-weight: 500;">▼ ここから有料部分（今週限定で無料公開中！） ▼</p>\n'
        full_content += clean_content(paid_text, title)

    ga4_tag = generate_ga4_tag()
    info = resolve_area_for_article(free_article)
    area_section = info["name"] if info else free_article.get("area", "")
    area_slug = info["slug"] if info else "tokyo-other"

    description = generate_meta_description(free_article)
    keywords = generate_meta_keywords(free_article)

    head_meta = generate_head_meta(
        title=title,
        description=description,
        url=f"/articles/{slug}/",
        page_type="article",
        image=free_article.get("thumbnail"),
        keywords=keywords,
        article_date=free_article.get("date"),
        article_section=area_section,
    )
    head_meta = inject_gsc_verification(head_meta)

    breadcrumb_items = [
        {"name": "ホーム", "url": "/"},
        {"name": "エリア一覧", "url": "/areas/"},
    ]
    if info:
        breadcrumb_items.append({"name": info["name"], "url": f"/areas/{info['slug']}/"})
    breadcrumb_items.append({"name": title[:40]})

    jsonld_parts = [
        generate_blogposting_jsonld(free_article),
        generate_breadcrumb_jsonld(breadcrumb_items),
    ]
    jsonld = "\n  ".join(jsonld_parts)

    breadcrumb_html = generate_breadcrumb_html(breadcrumb_items)
    related_html = generate_related_articles_block(free_article, all_articles, limit=6)
    area_nav_html = generate_area_nav_block(free_article, all_articles)

    html = template
    replacements = {
        "{{HEAD_META}}":          head_meta,
        "{{JSON_LD}}":            jsonld,
        "{{GA4_TAG}}":            ga4_tag,
        "{{BREADCRUMB_HTML}}":    breadcrumb_html,
        "{{TITLE}}":              escape_html(title),
        "{{DATE}}":               free_article.get("date", ""),
        "{{AREA_SLUG}}":          area_slug,
        "{{AREA_DISPLAY}}":       escape_html(area_section),
        "{{CONTENT}}":            full_content,
        "{{WAKUST_URL}}":         free_article.get("wakust_url", "https://wakust.com/"),
        "{{RELATED_ARTICLES}}":   related_html,
        "{{AREA_NAV_BLOCK}}":     area_nav_html,
    }
    for k, v in replacements.items():
        html = html.replace(k, v)

    # CTAを変更（全文公開中なので「他の記事も読む」に）
    html = html.replace(
        "この記事の全文はワクストで公開中！",
        "この記事を気に入っていただけたら、他の記事もチェック！"
    )
    html = html.replace("ワクストで全文を読む →", "ワクストで他の記事も読む →")

    with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  無料記事ページ: {title[:40]}... 生成完了（SEO強化）")


# ============================================================
# メイン
# ============================================================

def main():
    print("=== ビルド開始 (v4) ===")
    print(f"時刻: {datetime.now().isoformat()}")
    if GA4_ID:
        print(f"  GA4: {GA4_ID} ✓")
    if GSC_VERIFICATION:
        print(f"  GSC: verified ✓")

    if os.path.exists(PUBLIC_DIR):
        shutil.rmtree(PUBLIC_DIR)

    # 静的ファイルコピー
    # Search Console / Bing Webmaster認証ファイルを自動コピー
    import glob
    for pattern in ["google*.html", "BingSiteAuth.xml", "yandex_*.html"]:
        for verification_file in glob.glob(os.path.join(SITE_DIR, pattern)):
            dst = os.path.join(PUBLIC_DIR, os.path.basename(verification_file))
            os.makedirs(PUBLIC_DIR, exist_ok=True)
            shutil.copy2(verification_file, dst)
            print(f"  認証ファイル: {os.path.basename(verification_file)} コピー完了")

    for item in ["index.html", "css", "images", "CNAME"]:
        src = os.path.join(SITE_DIR, item)
        dst = os.path.join(PUBLIC_DIR, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    for subdir in ["articles", "shops", "about"]:
        src = os.path.join(SITE_DIR, subdir)
        dst = os.path.join(PUBLIC_DIR, subdir)
        if os.path.isdir(src):
            shutil.copytree(src, dst)

    # データ読み込み
    articles = load_json("articles.json")
    shops = load_json("shops.json")
    sale_articles = load_json("sale_articles.json")
    bestseller_articles = load_json("bestseller_articles.json")
    free_article = load_json("free_article.json")
    if isinstance(free_article, list):
        free_article = free_article[0] if free_article else {}

    print(f"データ: 記事 {len(articles)}件, 店舗 {len(shops)}件, セール {len(sale_articles)}件, 売れ筋 {len(bestseller_articles)}件")

    article_template = load_template("article.html")
    area_template = load_template("area.html")

    # エリアグルーピング
    area_groups = group_articles_by_area(articles)
    print(f"  エリア分類: {len(area_groups)}エリア")

    # 各ページ生成
    if articles:
        build_article_pages(articles, article_template, articles)

    build_index(articles, shops, sale_articles, bestseller_articles, free_article)
    build_articles_list(articles)

    # エリアページ生成（v4 新機能）
    ga4_tag = generate_ga4_tag()
    area_page_count = 0
    for area_slug, area_group in area_groups.items():
        if build_area_page(area_slug, area_group, area_groups, area_template, PUBLIC_DIR, ga4_tag):
            area_page_count += 1
    print(f"  エリアページ: {area_page_count}件 生成完了")

    build_area_index_page(area_groups, PUBLIC_DIR, ga4_tag)
    print("  エリア一覧トップ: 生成完了")

    if free_article and free_article.get("title"):
        build_free_article_page(free_article, article_template, articles)

    if shops:
        build_shops_list(shops)

    build_sitemap_and_robots(articles, shops, area_groups, free_article)

    print("=== ビルド完了 (v4) ===")
    print(f"出力先: {PUBLIC_DIR}")


if __name__ == "__main__":
    main()
