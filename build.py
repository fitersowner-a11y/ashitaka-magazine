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
from lib import beginner_guide


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

def build_sitemap_and_robots(articles, shops, area_groups, free_article, bg_result=None):
    sitemap_xml, count = build_sitemap_v2(articles, shops, area_groups, free_article, bg_result)
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
# 無料記事の全文ページ（v4.1 重複除去版）
# ============================================================

def _split_free_content(free_text):
    """free_contentを「無料部分」と「有料部分テキスト」に分割する。
    ワクストの「---ここから先は有料記事です---」マーカーを境界として使用。
    マーカーがなければ全文を無料部分として返す。
    """
    PAYWALL_MARKERS = [
        "---ここから先は有料記事です---",
        "ここから先は有料記事です",
        "---有料記事---",
    ]
    for marker in PAYWALL_MARKERS:
        if marker in free_text:
            parts = free_text.split(marker, 1)
            return parts[0].strip(), parts[1].strip()
    return free_text.strip(), ""


def _strip_html_to_plain(html_text):
    """HTMLタグ・エンティティを除去してプレーンテキストにする（重複比較用）"""
    text = re.sub(r'<[^>]+>', '', html_text)
    # HTMLエンティティを戻す
    for entity, char in [('&hellip;', '…'), ('&nbsp;', ' '), ('&amp;', '&'),
                         ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'),
                         ('&darr;', '↓'), ('&uarr;', '↑')]:
        text = text.replace(entity, char)
    # 空白・改行を全除去して比較用テキストに
    text = re.sub(r'\s+', '', text)
    return text


def _remove_nav_garbage(text):
    """free_contentの末尾にあるワクストのナビゲーション・プロフィール部分を除去"""
    GARBAGE_MARKERS = [
        "クリエイターのプロフィール",
        "記事を読みたい人ガイド",
        "この記事のURL",
        "おすすめタグ",
        "© ワクスト",
    ]
    for marker in GARBAGE_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx].strip()
    return text


def build_free_article_page(free_article, template, all_articles):
    """無料記事の全文ページを生成（v4.1 重複除去版）

    データの問題:
      - free_content に「---ここから先は有料記事です---」マーカーの後ろに
        有料部分テキストが含まれることがある
      - paid_content に無料部分のHTMLがそのまま含まれることがある
      - free_content 末尾にワクストのナビゲーションゴミが付くことがある

    修正ロジック:
      1. free_content をマーカーで「無料テキスト」と「有料テキスト(from free)」に分割
      2. ナビゲーションゴミを除去
      3. paid_content のプレーンテキストと free_part のプレーンテキストを比較
         → 重複している場合は paid_content から無料部分を除外
      4. 有料部分の決定: paid_content（重複除去済み）か、
         マーカー以降のテキスト（paid_from_free）を使用
    """
    if not free_article or not free_article.get("title"):
        return

    slug = free_article["slug"]
    title = free_article["title"]
    output_dir = os.path.join(PUBLIC_DIR, "articles", slug)
    os.makedirs(output_dir, exist_ok=True)

    # --- Step 1: free_content をマーカーで分割 ---
    raw_free = free_article.get("free_content", "")
    free_part, paid_from_free = _split_free_content(raw_free)

    # --- Step 2: ナビゲーションゴミ除去 ---
    free_part = _remove_nav_garbage(free_part)
    paid_from_free = _remove_nav_garbage(paid_from_free)

    # --- Step 3: paid_content の重複チェック ---
    paid_html = free_article.get("paid_content", "")
    actual_paid_html = ""

    if paid_html:
        # paid_content のプレーンテキストと free_part のプレーンテキストを比較
        paid_plain = _strip_html_to_plain(paid_html)
        free_plain = _strip_html_to_plain(free_part)

        # paid_content が free_part と同じ内容なら → 有料固有の内容なし
        # paid_content が free_part を含んでいるなら → free_part 以降が有料部分
        if paid_plain and free_plain:
            # 先頭100文字で重複判定（完全一致だと微妙な差で漏れるので）
            check_len = min(100, len(free_plain), len(paid_plain))
            if check_len > 20 and paid_plain[:check_len] == free_plain[:check_len]:
                # paid_content は free_part と重複している
                # → paid_content 全体が無料部分と同じなら、有料固有部分なし
                if len(paid_plain) <= len(free_plain) * 1.1:
                    # ほぼ同じ長さ → 重複。paid_from_free を使う
                    actual_paid_html = ""
                    print(f"    ⚠ paid_content は free_content と重複 → paid_from_free を使用")
                else:
                    # paid_content の方が長い → 後半に有料固有部分がある可能性
                    # ただし分離が困難なので paid_from_free を優先
                    actual_paid_html = ""
                    print(f"    ⚠ paid_content 先頭が重複 → paid_from_free を使用")
            else:
                # 重複なし → paid_content をそのまま使用
                actual_paid_html = paid_html
        else:
            actual_paid_html = paid_html

    # --- Step 4: 有料部分の決定 ---
    # paid_from_free（マーカー以降のテキスト）があればそちらを優先
    if paid_from_free:
        final_paid = paid_from_free
        paid_is_html = False
    elif actual_paid_html:
        final_paid = actual_paid_html
        paid_is_html = True
    else:
        final_paid = ""
        paid_is_html = False

    # --- Step 5: HTML生成 ---
    # 無料部分のHTML化
    if free_part and not free_part.strip().startswith("<"):
        free_html = "\n".join(f"<p>{p.strip()}</p>" for p in free_part.split("\n") if p.strip())
    else:
        free_html = free_part

    full_content = clean_content(free_html, title)

    if final_paid:
        full_content += '\n<hr style="margin: 2em 0; border: none; border-top: 2px dashed var(--primary);">\n'
        full_content += '<p style="text-align:center; color: var(--primary); font-weight: 500;">▼ ここから有料部分（今週限定で無料公開中！） ▼</p>\n'
        if paid_is_html:
            full_content += clean_content(final_paid, title)
        else:
            # プレーンテキスト → HTML化
            paid_html_lines = "\n".join(
                f"<p>{p.strip()}</p>" for p in final_paid.split("\n") if p.strip()
            )
            full_content += clean_content(paid_html_lines, title)

    # --- 以下はv4と同じ（SEOメタ等） ---
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

    print(f"  無料記事ページ: {title[:40]}... 生成完了（v4.1 重複除去版）")


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

    # 初心者ガイド生成
    bg_templates = {
        "index":      load_template("beginner_guide_index.html"),
        "episode":    load_template("beginner_guide_episode.html"),
        "characters": load_template("beginner_guide_characters.html"),
    }
    bg_data_path = os.path.join(DATA_DIR, "beginner_guide.json")
    if os.path.exists(bg_data_path):
        bg_result = beginner_guide.build_all(
            data_path=bg_data_path,
            all_articles=articles,
            area_data=area_groups,
            templates=bg_templates,
            output_dir=os.path.join(PUBLIC_DIR, "beginner-guide"),
            ga4_tag=ga4_tag,
        )
        # 画像ソース（リポジトリ管理）→ public へコピー
        src_bg_images = os.path.join(SITE_DIR, "beginner-guide", "images")
        dst_bg_images = os.path.join(PUBLIC_DIR, "beginner-guide", "images")
        if os.path.isdir(src_bg_images):
            if os.path.exists(dst_bg_images):
                shutil.rmtree(dst_bg_images)
            shutil.copytree(src_bg_images, dst_bg_images)
            print("  初心者ガイド画像: コピー完了")
    else:
        print("  警告: data/beginner_guide.json が見つかりません。初心者ガイドをスキップ。")
        bg_result = None

    if free_article and free_article.get("title"):
        build_free_article_page(free_article, article_template, articles)

    if shops:
        build_shops_list(shops)

    build_sitemap_and_robots(articles, shops, area_groups, free_article, bg_result)

    print("=== ビルド完了 (v4) ===")
    print(f"出力先: {PUBLIC_DIR}")


if __name__ == "__main__":
    main()
