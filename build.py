#!/usr/bin/env python3
"""
ビルドスクリプト v3

改善点:
- モック記事を除去（articles.json が空なら「まだ記事がありません」表示）
- 今週のセール記事セクション対応（sale_articles.json）
- 記事カードに data-area 属性を付与（カテゴリーフィルター用）
- sitemap.xml / robots.txt を自動生成
- 構造化データ (JSON-LD) を記事ページに埋め込み
"""

import json
import os
import re
import shutil
from datetime import datetime

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SITE_DIR, "data")
TEMPLATE_DIR = os.path.join(SITE_DIR, "templates")
PUBLIC_DIR = os.path.join(SITE_DIR, "public")
SITE_URL = "https://menesthe-ashitaka.com"
SITE_NAME = "メンエス好きのアシタカマガジン"


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
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def area_to_filter_key(area):
    """エリア名をフィルター用のキーに変換"""
    mapping = {
        "東京都": "tokyo", "新宿": "tokyo", "池袋": "tokyo", "多摩": "tokyo",
        "神奈川県": "kanagawa",
        "埼玉県": "saitama",
        "千葉県": "chiba",
        "大阪府": "osaka", "日本橋": "osaka",
        "愛知県": "aichi", "栄": "aichi",
        "兵庫県": "hyogo",
        "福岡県": "fukuoka",
    }
    return mapping.get(area, "other")


def generate_article_card(article, with_data_area=False):
    """記事カードHTMLを生成"""
    thumb = article.get("thumbnail", "")
    title_escaped = escape_html(article["title"])
    if thumb:
        thumb_html = f'<img src="{thumb}" alt="{title_escaped}" loading="lazy">'
    else:
        thumb_html = '<span class="placeholder">📝</span>'

    area = article.get("area", "")
    area_key = area_to_filter_key(area)
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


def generate_structured_data(article):
    url = f"{SITE_URL}/articles/{article['slug']}/"
    structured = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": article["title"],
        "description": article.get("excerpt", ""),
        "datePublished": article["date"],
        "dateModified": article["date"],
        "author": {"@type": "Person", "name": "メンエス好きのアシタカ"},
        "publisher": {"@type": "Organization", "name": SITE_NAME},
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "url": url
    }
    if article.get("thumbnail"):
        structured["image"] = article["thumbnail"]
    return f'<script type="application/ld+json">{json.dumps(structured, ensure_ascii=False)}</script>'


def build_article_pages(articles, template):
    for article in articles:
        slug = article["slug"]
        output_dir = os.path.join(PUBLIC_DIR, "articles", slug)
        os.makedirs(output_dir, exist_ok=True)
        html = template
        html = html.replace("{{TITLE}}", escape_html(article["title"]))
        html = html.replace("{{DATE}}", article["date"])
        html = html.replace("{{AREA}}", escape_html(article.get("area", "")))
        html = html.replace("{{EXCERPT}}", escape_html(article.get("excerpt", "")))
        html = html.replace("{{SLUG}}", slug)
        html = html.replace("{{CONTENT}}", article.get("content", ""))
        html = html.replace("{{WAKUST_URL}}", article.get("wakust_url", "https://wakust.com/"))
        html = html.replace("{{RELATED_ARTICLES}}", "")
        structured = generate_structured_data(article)
        html = html.replace("</head>", f"{structured}\n</head>")
        if article.get("thumbnail"):
            if 'property="og:image"' not in html:
                html = html.replace("</head>", f'<meta property="og:image" content="{article["thumbnail"]}">\n</head>')
        with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)
    print(f"  記事ページ: {len(articles)}件 生成完了")


def generate_featured_card(article, card_type="green"):
    """無料記事またはセール記事の大きめカードHTMLを生成"""
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
    """ランキングアイテムHTMLを生成"""
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
    index_path = os.path.join(PUBLIC_DIR, "index.html")
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
            rf'\1{featured_html}\2',
            html,
            flags=re.DOTALL,
        )
        html = html.replace('id="featuredSection" style="display:none;"', 'id="featuredSection"')

    # === 最新記事 ===
    if articles:
        latest = sorted(articles, key=lambda a: a["date"], reverse=True)[:3]
        cards_html = "".join(generate_article_card(a) for a in latest)
    else:
        cards_html = '<div style="text-align:center;padding:40px;color:#888;">記事を準備中です。もうしばらくお待ちください。</div>'

    html = re.sub(
        r'(<div class="articles-grid" id="latestArticles">).*?(</div>\s*</section>)',
        rf'\1{cards_html}\2',
        html,
        flags=re.DOTALL,
    )

    # === 売れ筋ランキング ===
    # 今週（bestseller_articles = 72h売上ランキング）
    if bestseller_articles:
        weekly_html = ""
        for i, a in enumerate(bestseller_articles[:10]):
            weekly_html += generate_ranking_item(a, i + 1)
    else:
        weekly_html = '<div style="text-align:center;padding:30px;color:#888;">データ取得中です</div>'

    html = re.sub(
        r'(<div class="ranking-list" id="rankWeekly">)\s*(</div>)',
        rf'\1{weekly_html}\2',
        html,
        flags=re.DOTALL,
    )

    # 総計（all_articles_data.json から売上順で取得）
    all_data = load_json("all_articles_data.json")
    if all_data:
        sorted_all = sorted(all_data, key=lambda a: a.get("sales_amount", 0), reverse=True)[:10]
        total_html = ""
        for i, a in enumerate(sorted_all):
            total_html += generate_ranking_item(a, i + 1)
    else:
        total_html = '<div style="text-align:center;padding:30px;color:#888;">データ取得中です</div>'

    html = re.sub(
        r'(<div class="ranking-list" id="rankTotal" style="display:none;">)\s*(</div>)',
        rf'\1{total_html}\2',
        html,
        flags=re.DOTALL,
    )

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("  トップページ: 更新完了")


def build_articles_list(articles):
    list_path = os.path.join(PUBLIC_DIR, "articles", "index.html")
    with open(list_path, "r", encoding="utf-8") as f:
        html = f.read()

    sorted_articles = sorted(articles, key=lambda a: a["date"], reverse=True)

    # カテゴリーフィルターを記事データから動的に生成
    areas_seen = {}
    for a in sorted_articles:
        area = a.get("area", "")
        if area:
            key = area_to_filter_key(area)
            if key not in areas_seen:
                areas_seen[key] = area

    filter_buttons = '<button class="filter-btn active" data-filter="all">すべて</button>\n'
    for key, label in areas_seen.items():
        filter_buttons += f'        <button class="filter-btn" data-filter="{key}">{escape_html(label)}</button>\n'

    # フィルターボタンを差し替え
    html = re.sub(
        r'(<div class="shops-filter"[^>]*>).*?(</div>)',
        rf'\1\n        {filter_buttons}      \2',
        html,
        flags=re.DOTALL,
    )

    # 記事カード生成（data-area属性付き）
    if sorted_articles:
        cards_html = "".join(generate_article_card(a, with_data_area=True) for a in sorted_articles)
    else:
        cards_html = '<div style="text-align:center;padding:40px;color:#888;">記事を準備中です。もうしばらくお待ちください。</div>'

    html = re.sub(
        r'(<div class="articles-grid" id="articlesList">).*?(</div>\s*</section>)',
        rf'\1{cards_html}\2',
        html,
        flags=re.DOTALL,
    )

    # フィルタリングJSを実際に動作するものに差し替え
    new_script = """<script>
    function toggleMenu() {
      document.getElementById('siteNav').classList.toggle('open');
    }

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

    html = re.sub(
        r'<script>.*?</script>',
        new_script,
        html,
        flags=re.DOTALL,
    )

    with open(list_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("  記事一覧ページ: 更新完了")


def build_shops_list(shops):
    list_path = os.path.join(PUBLIC_DIR, "shops", "index.html")
    with open(list_path, "r", encoding="utf-8") as f:
        html = f.read()
    shops_html = "".join(generate_shop_card(s) for s in shops)
    html = re.sub(
        r'(<div class="shops-grid" id="shopsList">).*?(</div>\s*</section>)',
        rf'\1{shops_html}\2',
        html,
        flags=re.DOTALL,
    )
    with open(list_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("  店舗一覧ページ: 更新完了")


def build_sitemap(articles, shops):
    now = datetime.now().strftime("%Y-%m-%d")
    urls = []
    for path, freq, pri in [("", "daily", "1.0"), ("articles/", "daily", "0.9"),
                             ("shops/", "weekly", "0.8"), ("about/", "monthly", "0.5")]:
        urls.append(f'  <url><loc>{SITE_URL}/{path}</loc><lastmod>{now}</lastmod><changefreq>{freq}</changefreq><priority>{pri}</priority></url>')
    for a in articles:
        urls.append(f'  <url><loc>{SITE_URL}/articles/{a["slug"]}/</loc><lastmod>{a.get("date", now)}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>')
    for s in shops:
        urls.append(f'  <url><loc>{SITE_URL}/shops/{s["slug"]}/</loc><lastmod>{now}</lastmod><changefreq>monthly</changefreq><priority>0.6</priority></url>')
    with open(os.path.join(PUBLIC_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{chr(10).join(urls)}\n</urlset>\n')
    print(f"  sitemap.xml: {len(urls)}件 生成完了")


def build_robots_txt():
    with open(os.path.join(PUBLIC_DIR, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n")
    print("  robots.txt: 生成完了")


def build_free_article_page(free_article, template):
    """無料公開記事の全文ページを生成"""
    if not free_article or not free_article.get("title"):
        return

    slug = free_article["slug"]
    output_dir = os.path.join(PUBLIC_DIR, "articles", slug)
    os.makedirs(output_dir, exist_ok=True)

    # 無料本文 + 有料本文を結合
    free_text = free_article.get("free_content", "")
    paid_text = free_article.get("paid_content", "")

    # 無料本文をHTML化（プレーンテキストの場合）
    if free_text and not free_text.strip().startswith("<"):
        free_html = "\n".join(f"<p>{p.strip()}</p>" for p in free_text.split("\n") if p.strip())
    else:
        free_html = free_text

    # 全文を結合
    full_content = free_html
    if paid_text:
        full_content += '\n<hr style="margin: 2em 0; border: none; border-top: 2px dashed var(--primary);">\n'
        full_content += '<p style="text-align:center; color: var(--primary); font-weight: 500; margin-bottom: 1.5em;">▼ ここから有料部分（今週限定で無料公開中！） ▼</p>\n'
        full_content += paid_text

    html = template
    html = html.replace("{{TITLE}}", escape_html(free_article["title"]))
    html = html.replace("{{DATE}}", free_article.get("date", ""))
    html = html.replace("{{AREA}}", escape_html(free_article.get("area", "")))
    html = html.replace("{{EXCERPT}}", escape_html(free_article.get("excerpt", "")))
    html = html.replace("{{SLUG}}", slug)
    html = html.replace("{{CONTENT}}", full_content)
    html = html.replace("{{WAKUST_URL}}", free_article.get("wakust_url", "https://wakust.com/"))
    html = html.replace("{{RELATED_ARTICLES}}", "")

    # CTAを変更（全文公開中なので「他の記事も読む」に）
    html = html.replace(
        "この記事の全文はワクストで公開中！",
        "この記事を気に入っていただけたら、他の記事もチェック！"
    )
    html = html.replace(
        "ワクストで全文を読む →",
        "ワクストで他の記事も読む →"
    )

    # 構造化データ
    structured = generate_structured_data({
        "title": free_article["title"],
        "excerpt": free_article.get("excerpt", ""),
        "date": free_article.get("date", ""),
        "slug": slug,
        "thumbnail": free_article.get("thumbnail", ""),
    })
    html = html.replace("</head>", f"{structured}\n</head>")

    if free_article.get("thumbnail"):
        if 'property="og:image"' not in html:
            html = html.replace("</head>", f'<meta property="og:image" content="{free_article["thumbnail"]}">\n</head>')

    with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  無料記事ページ: {free_article['title'][:40]}... 生成完了")


def main():
    print("=== ビルド開始 ===")
    print(f"時刻: {datetime.now().isoformat()}")

    if os.path.exists(PUBLIC_DIR):
        shutil.rmtree(PUBLIC_DIR)

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

    articles = load_json("articles.json")
    shops = load_json("shops.json")
    sale_articles = load_json("sale_articles.json")
    bestseller_articles = load_json("bestseller_articles.json")
    free_article = load_json("free_article.json")
    if isinstance(free_article, list):
        free_article = free_article[0] if free_article else {}

    print(f"データ: 記事 {len(articles)}件, 店舗 {len(shops)}件, セール {len(sale_articles)}件, 売れ筋 {len(bestseller_articles)}件")
    if free_article and free_article.get("title"):
        print(f"  無料記事: {free_article['title'][:40]}...")

    article_template = load_template("article.html")

    if articles:
        build_article_pages(articles, article_template)
    build_index(articles, shops, sale_articles, bestseller_articles, free_article)
    build_articles_list(articles)

    if free_article and free_article.get("title"):
        build_free_article_page(free_article, article_template)

    if shops:
        build_shops_list(shops)

    build_sitemap(articles, shops)
    build_robots_txt()

    print("=== ビルド完了 ===")
    print(f"出力先: {PUBLIC_DIR}")


if __name__ == "__main__":
    main()
