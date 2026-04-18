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


def build_index(articles, shops, sale_articles, bestseller_articles):
    index_path = os.path.join(PUBLIC_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    # セール記事セクション
    if sale_articles:
        sale_cards = "".join(generate_article_card(a) for a in sale_articles)
        html = re.sub(
            r'(<div class="articles-grid" id="saleArticles">)\s*(</div>)',
            rf'\1{sale_cards}\2',
            html,
            flags=re.DOTALL,
        )
        html = html.replace('id="saleSection" style="display:none;"', 'id="saleSection"')

    # 最新記事
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

    # 売れ筋記事（3x3=9件）
    if bestseller_articles:
        bs_cards = "".join(generate_article_card(a) for a in bestseller_articles[:9])
    else:
        bs_cards = '<div style="text-align:center;padding:40px;color:#888;">売れ筋データを取得中です。</div>'

    html = re.sub(
        r'(<div class="articles-grid articles-grid-3x3" id="bestsellerArticles">)\s*(</div>)',
        rf'\1{bs_cards}\2',
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

    print(f"データ: 記事 {len(articles)}件, 店舗 {len(shops)}件, セール {len(sale_articles)}件, 売れ筋 {len(bestseller_articles)}件")

    article_template = load_template("article.html")

    if articles:
        build_article_pages(articles, article_template)
    build_index(articles, shops, sale_articles, bestseller_articles)
    build_articles_list(articles)

    if shops:
        build_shops_list(shops)

    build_sitemap(articles, shops)
    build_robots_txt()

    print("=== ビルド完了 ===")
    print(f"出力先: {PUBLIC_DIR}")


if __name__ == "__main__":
    main()
