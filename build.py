#!/usr/bin/env python3
"""
ビルドスクリプト: articles.json と shops.json から静的HTMLを生成する

使い方:
  python3 build.py

データファイル:
  data/articles.json  — 記事データ
  data/shops.json     — 店舗データ

出力:
  public/ — デプロイ用ファイル一式
"""

import json
import os
import shutil
from datetime import datetime

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SITE_DIR, "data")
TEMPLATE_DIR = os.path.join(SITE_DIR, "templates")
PUBLIC_DIR = os.path.join(SITE_DIR, "public")


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


def generate_article_card(article):
    """記事カードHTMLを生成"""
    thumb = article.get("thumbnail", "")
    if thumb:
        thumb_html = f'<img src="{thumb}" alt="{article["title"]}" loading="lazy">'
    else:
        thumb_html = '<span class="placeholder">📝</span>'

    return f'''
    <div class="article-card">
      <a href="/articles/{article["slug"]}/">
        <div class="article-thumb">{thumb_html}</div>
        <div class="article-body">
          <div class="article-meta">{article.get("area", "")} ・ {article["date"]}</div>
          <h3 class="article-title">{article["title"]}</h3>
          <p class="article-excerpt">{article.get("excerpt", "")}</p>
          <span class="article-read-more">続きを読む →</span>
        </div>
      </a>
    </div>'''


def generate_shop_card(shop):
    """店舗カードHTMLを生成"""
    tags_html = ""
    for tag in shop.get("tags", []):
        color = tag.get("color", "blue")
        tags_html += f'<span class="tag {color}">{tag["label"]}</span>'

    return f'''
    <a href="/shops/{shop["slug"]}/" class="shop-card">
      <div class="shop-icon">{shop["name"][0]}</div>
      <div class="shop-info">
        <h3>{shop["name"]}</h3>
        <p class="shop-location">{shop.get("area", "")} ・ {shop.get("type", "")}</p>
        <div class="shop-tags">{tags_html}</div>
      </div>
    </a>'''


def build_article_pages(articles, template):
    """各記事の個別ページを生成"""
    for article in articles:
        slug = article["slug"]
        output_dir = os.path.join(PUBLIC_DIR, "articles", slug)
        os.makedirs(output_dir, exist_ok=True)

        html = template
        html = html.replace("{{TITLE}}", article["title"])
        html = html.replace("{{DATE}}", article["date"])
        html = html.replace("{{AREA}}", article.get("area", ""))
        html = html.replace("{{EXCERPT}}", article.get("excerpt", ""))
        html = html.replace("{{SLUG}}", slug)
        html = html.replace("{{CONTENT}}", article.get("content", ""))
        html = html.replace("{{WAKUST_URL}}", article.get("wakust_url", "https://wakust.com/"))
        html = html.replace("{{RELATED_ARTICLES}}", "")

        with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)

    print(f"  記事ページ: {len(articles)}件 生成完了")


def build_index(articles, shops):
    """トップページの記事・店舗カードを差し替え"""
    index_path = os.path.join(PUBLIC_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    # 最新記事3件のカードを生成
    latest = sorted(articles, key=lambda a: a["date"], reverse=True)[:3]
    cards_html = "".join(generate_article_card(a) for a in latest)

    # latestArticles div の中身を差し替え
    import re
    html = re.sub(
        r'(<div class="articles-grid" id="latestArticles">).*?(</div>\s*</section>)',
        rf'\1{cards_html}\2',
        html,
        flags=re.DOTALL,
    )

    # おすすめ店舗4件のカードを生成
    recommended = shops[:4]
    shops_html = "".join(generate_shop_card(s) for s in recommended)

    html = re.sub(
        r'(<div class="shops-grid" id="recommendedShops">).*?(</div>\s*</section>)',
        rf'\1{shops_html}\2',
        html,
        flags=re.DOTALL,
    )

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)

    print("  トップページ: 更新完了")


def build_articles_list(articles):
    """記事一覧ページを更新"""
    list_path = os.path.join(PUBLIC_DIR, "articles", "index.html")
    with open(list_path, "r", encoding="utf-8") as f:
        html = f.read()

    sorted_articles = sorted(articles, key=lambda a: a["date"], reverse=True)
    cards_html = "".join(generate_article_card(a) for a in sorted_articles)

    import re
    html = re.sub(
        r'(<div class="articles-grid" id="articlesList">).*?(</div>\s*</section>)',
        rf'\1{cards_html}\2',
        html,
        flags=re.DOTALL,
    )

    with open(list_path, "w", encoding="utf-8") as f:
        f.write(html)

    print("  記事一覧ページ: 更新完了")


def build_shops_list(shops):
    """店舗一覧ページを更新"""
    list_path = os.path.join(PUBLIC_DIR, "shops", "index.html")
    with open(list_path, "r", encoding="utf-8") as f:
        html = f.read()

    shops_html = "".join(generate_shop_card(s) for s in shops)

    import re
    html = re.sub(
        r'(<div class="shops-grid" id="shopsList">).*?(</div>\s*</section>)',
        rf'\1{shops_html}\2',
        html,
        flags=re.DOTALL,
    )

    with open(list_path, "w", encoding="utf-8") as f:
        f.write(html)

    print("  店舗一覧ページ: 更新完了")


def main():
    print("=== ビルド開始 ===")
    print(f"時刻: {datetime.now().isoformat()}")

    # public ディレクトリを初期化
    if os.path.exists(PUBLIC_DIR):
        shutil.rmtree(PUBLIC_DIR)

    # 静的ファイルをコピー
    for item in ["index.html", "css", "images"]:
        src = os.path.join(SITE_DIR, item)
        dst = os.path.join(PUBLIC_DIR, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    # サブページをコピー
    for subdir in ["articles", "shops", "about"]:
        src = os.path.join(SITE_DIR, subdir)
        dst = os.path.join(PUBLIC_DIR, subdir)
        if os.path.isdir(src):
            shutil.copytree(src, dst)

    # データ読み込み
    articles = load_json("articles.json")
    shops = load_json("shops.json")

    print(f"データ: 記事 {len(articles)}件, 店舗 {len(shops)}件")

    # 記事テンプレート読み込み
    article_template = load_template("article.html")

    # ビルド実行
    if articles:
        build_article_pages(articles, article_template)
        build_index(articles, shops)
        build_articles_list(articles)

    if shops:
        build_shops_list(shops)

    print("=== ビルド完了 ===")
    print(f"出力先: {PUBLIC_DIR}")


if __name__ == "__main__":
    main()
