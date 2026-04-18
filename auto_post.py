#!/usr/bin/env python3
"""
ワクスト自動投稿スクリプト (auto_post.py) v4

v3からの修正:
- ページネーション対応: 全ページを巡回して記事を取得（20件/ページ）
"""

import json
import os
import re
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE_URL = "https://wakust.com/user/ryu-1992/?sort=postd"
ARTICLES_JSON = Path(__file__).parent / "data" / "articles.json"
MAX_POSTS_PER_RUN = 3
MAX_PAGES = 10  # 最大巡回ページ数（安全弁）
EXCERPT_MAX_CHARS = 500
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

SIDEBAR_CATEGORIES = {
    "北海道", "東北", "北関東", "静岡県", "甲信越北陸", "中国", "四国", "九州", "海外",
    "ノウハウ(ネット)", "ノウハウ(リアル)", "美容健康", "R18小説", "ラウンジ",
    "イケメン", "関西", "岐阜三重", "栄", "日本橋"
}


def load_articles():
    if not ARTICLES_JSON.exists():
        return []
    with open(ARTICLES_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def save_articles(articles):
    ARTICLES_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(ARTICLES_JSON, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)


def accept_age_modal(page):
    time.sleep(1)
    try:
        page.evaluate("""
            () => {
                const allElements = document.querySelectorAll('a, button, span, div');
                for (const el of allElements) {
                    if ((el.textContent || '').trim() === 'はい') {
                        try { el.click(); break; } catch (e) {}
                    }
                }
                document.cookie = 'age_check=1; path=/; domain=.wakust.com';
                document.cookie = 'adult_check=1; path=/; domain=.wakust.com';
            }
        """)
    except Exception:
        pass


def extract_articles_from_page(page):
    """現在のページから記事リンクを抽出"""
    return page.evaluate("""
        () => {
            const results = [];
            const seen = new Set();
            const allLinks = document.querySelectorAll('a[href]');

            for (const link of allLinks) {
                const href = link.getAttribute('href') || '';
                const match = href.match(/\\/ryu-1992\\/(\\d{4,})\\/?(?:\\?.*)?$/);
                if (!match) continue;

                const articleId = match[1];
                if (seen.has(articleId)) continue;

                const title = (link.textContent || '').trim();
                if (!title || title.length < 5) continue;
                if (title === 'もっと読む' || title === '続きを読む' || title === 'NEW') continue;

                seen.add(articleId);
                const absoluteUrl = href.startsWith('http') ? href : 'https://wakust.com' + href;

                results.push({
                    id: articleId,
                    url: absoluteUrl,
                    title: title
                });
            }
            return results;
        }
    """)


def has_next_page(page):
    """次のページがあるかを確認"""
    return page.evaluate("""
        () => {
            // 「次」「>」「>>」「次へ」のリンクを探す
            const links = document.querySelectorAll('a[href]');
            for (const link of links) {
                const href = link.getAttribute('href') || '';
                const text = (link.textContent || '').trim();
                // paged パラメータが含まれるリンク
                if (href.includes('paged=') && (text === '次' || text === '>' || text === '>>' || text === '次へ' || text === '›' || text === '»')) {
                    return true;
                }
            }
            // または paged= の数字が現在より大きいリンクがあるか
            const currentMatch = window.location.search.match(/paged=(\\d+)/);
            const currentPage = currentMatch ? parseInt(currentMatch[1]) : 1;
            for (const link of links) {
                const href = link.getAttribute('href') || '';
                const pageMatch = href.match(/paged=(\\d+)/);
                if (pageMatch && parseInt(pageMatch[1]) > currentPage) {
                    return true;
                }
            }
            return false;
        }
    """)


def fetch_all_articles(page):
    """全ページを巡回して記事一覧を取得"""
    page.context.add_cookies([
        {"name": "age_check", "value": "1", "domain": ".wakust.com", "path": "/"},
        {"name": "adult_check", "value": "1", "domain": ".wakust.com", "path": "/"},
    ])

    all_articles = []
    seen_ids = set()

    for page_num in range(1, MAX_PAGES + 1):
        if page_num == 1:
            url = BASE_URL
        else:
            url = f"{BASE_URL}&paged={page_num}"

        print(f"[INFO] ページ {page_num} を取得: {url}")
        page.goto(url, wait_until="networkidle", timeout=60000)
        time.sleep(3)

        if page_num == 1:
            accept_age_modal(page)
            time.sleep(2)

        articles = extract_articles_from_page(page)

        # 新しい記事がなければ最終ページ
        new_count = 0
        for a in articles:
            if a["id"] not in seen_ids:
                seen_ids.add(a["id"])
                all_articles.append(a)
                new_count += 1

        print(f"[INFO] ページ {page_num}: {len(articles)}件取得 (新規: {new_count}件)")

        if new_count == 0:
            print("[INFO] 新しい記事がないため、巡回を終了")
            break

        # 次のページがあるか確認
        if not has_next_page(page):
            print("[INFO] 最終ページに到達")
            break

        time.sleep(2)  # サーバー負荷軽減

    print(f"[INFO] 全ページ合計: {len(all_articles)}件")
    return all_articles


def fetch_article_detail(page, article_url):
    """記事詳細ページから本文、日付、カテゴリー、サムネイルを取得"""
    print(f"[INFO] 記事詳細を取得: {article_url}")
    page.goto(article_url, wait_until="networkidle", timeout=60000)
    time.sleep(2)
    accept_age_modal(page)
    time.sleep(2)

    sidebar_cats = json.dumps(list(SIDEBAR_CATEGORIES), ensure_ascii=False)

    detail = page.evaluate(f"""
        () => {{
            const SIDEBAR_CATS = new Set({sidebar_cats});

            let title = '';
            const ogTitle = document.querySelector('meta[property="og:title"]');
            if (ogTitle && ogTitle.content) {{
                title = ogTitle.content.trim();
            }}
            if (!title) {{
                const h1s = document.querySelectorAll('h1');
                for (const h1 of h1s) {{
                    const t = (h1.textContent || '').trim();
                    if (t && t !== 'ワクスト' && t.length > title.length) {{
                        title = t;
                    }}
                }}
            }}

            let dateStr = '';
            const bodyText = document.body.innerText || '';
            const dateMatch = bodyText.match(/(\\d{{4}})年(\\d{{2}})月(\\d{{2}})日/);
            if (dateMatch) {{
                dateStr = dateMatch[1] + '-' + dateMatch[2] + '-' + dateMatch[3];
            }}

            let area = '';
            const mainArea = document.querySelector('article') ||
                            document.querySelector('main') ||
                            document.querySelector('.post-content') ||
                            document.body;
            const catLinks = mainArea.querySelectorAll('a[href*="/post-category/"]');
            for (const el of catLinks) {{
                const txt = el.textContent.trim();
                if (!txt || txt.length > 20) continue;
                const parent = el.closest('nav, aside, .sidebar, header');
                if (parent) continue;
                area = txt;
                break;
            }}
            if (!area) {{
                const allCatLinks = document.querySelectorAll('a[href*="/post-category/"]');
                const likelyAreas = ['東京都', '神奈川県', '埼玉県', '千葉県', '多摩',
                                      '新宿', '池袋', '愛知県', '大阪府', '兵庫県',
                                      '福岡県', 'ノウハウ(ネット)', 'ノウハウ(リアル)'];
                for (const el of allCatLinks) {{
                    const txt = el.textContent.trim();
                    if (likelyAreas.includes(txt)) {{
                        area = txt;
                        break;
                    }}
                }}
            }}

            let thumbnail = '';
            const ogImage = document.querySelector('meta[property="og:image"]');
            if (ogImage && ogImage.content) {{
                thumbnail = ogImage.content;
            }}
            if (!thumbnail) {{
                const articleImg = mainArea.querySelector('img[src*="wp-content/uploads"]');
                if (articleImg && articleImg.src) {{
                    thumbnail = articleImg.src;
                }}
            }}

            let content = '';
            const mainText = bodyText;
            const purchaseIdx = mainText.indexOf('を購入する');
            if (purchaseIdx > 0) {{
                content = mainText.substring(0, purchaseIdx);
            }} else {{
                const registerIdx = mainText.indexOf('購入するには');
                if (registerIdx > 0) {{
                    content = mainText.substring(0, registerIdx);
                }} else {{
                    content = mainText.substring(0, 2000);
                }}
            }}

            const bodyStartMarkers = ['こんにちは', 'こんばんは', 'どうも', 'ども、',
                                       'はじめまして', 'はじめに', 'お疲れ'];
            let bodyStartIdx = -1;
            for (const marker of bodyStartMarkers) {{
                const idx = content.indexOf(marker);
                if (idx >= 0 && (bodyStartIdx === -1 || idx < bodyStartIdx)) {{
                    bodyStartIdx = idx;
                }}
            }}

            if (bodyStartIdx >= 0) {{
                content = content.substring(bodyStartIdx);
            }} else {{
                const lines = content.split('\\n').map(l => l.trim()).filter(l => l);
                content = lines.slice(Math.min(8, Math.floor(lines.length / 3))).join('\\n');
            }}

            return {{ title, dateStr, area, content, thumbnail }};
        }}
    """)

    return detail


def slugify_from_id(article_id):
    return f"wakust-{article_id}"


def truncate_content(content, max_chars=EXCERPT_MAX_CHARS):
    if len(content) <= max_chars:
        return content
    truncated = content[:max_chars]
    last_period = truncated.rfind("。")
    if last_period > max_chars * 0.5:
        truncated = truncated[:last_period + 1]
    return truncated


def make_excerpt(content, max_chars=100):
    first_para = content.split("\n")[0] if "\n" in content else content[:200]
    return truncate_content(first_para, max_chars)


def content_to_html(content):
    paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
    return "\n".join(f"<p>{p}</p>" for p in paragraphs)


def build_article_entry(detail, article_url, article_id, fallback_title=""):
    content_truncated = truncate_content(detail["content"], EXCERPT_MAX_CHARS)
    return {
        "slug": slugify_from_id(article_id),
        "title": detail["title"] or fallback_title,
        "date": detail["dateStr"] or datetime.now().strftime("%Y-%m-%d"),
        "area": detail["area"] or "",
        "excerpt": make_excerpt(detail["content"]),
        "content": content_to_html(content_truncated),
        "wakust_url": article_url,
        "thumbnail": detail.get("thumbnail", ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="書き込まず確認のみ")
    parser.add_argument("--max", type=int, default=MAX_POSTS_PER_RUN, help="最大投稿数")
    args = parser.parse_args()

    print(f"=== ワクスト自動投稿 開始 ({datetime.now().isoformat()}) ===")
    print(f"最大投稿数: {args.max}")
    print(f"Dry run: {args.dry_run}")

    existing = load_articles()
    existing_ids = {
        art["slug"].replace("wakust-", "")
        for art in existing
        if art["slug"].startswith("wakust-")
    }
    print(f"既存の記事数: {len(existing)} (ワクスト由来: {len(existing_ids)})")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale="ja-JP",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        try:
            # 全ページ巡回して記事一覧取得
            articles = fetch_all_articles(page)
            if not articles:
                print("[WARN] 記事が取得できませんでした。終了します。")
                return

            new_articles = [a for a in articles if a["id"] not in existing_ids]
            print(f"[INFO] 未登録の記事: {len(new_articles)}件")

            if not new_articles:
                print("[INFO] 新しい記事はありません。終了します。")
                return

            to_post = new_articles[: args.max]
            print(f"[INFO] 今回投稿する記事: {len(to_post)}件")

            new_entries = []
            for i, article in enumerate(to_post):
                try:
                    print(f"[INFO] ({i+1}/{len(to_post)}) 記事詳細を取得中...")
                    detail = fetch_article_detail(page, article["url"])
                    if not detail["content"] or len(detail["content"]) < 50:
                        print(f"[WARN] 本文が取得できませんでした: {article['url']}")
                        continue

                    entry = build_article_entry(
                        detail, article["url"], article["id"],
                        fallback_title=article.get("title", "")
                    )
                    new_entries.append(entry)
                    print(f"[OK] 記事追加: {entry['title'][:50]}")
                    print(f"     date: {entry['date']}, area: {entry['area']}")
                    print(f"     サムネイル: {entry['thumbnail'][:80] if entry['thumbnail'] else '(なし)'}")
                    time.sleep(2)
                except Exception as e:
                    print(f"[ERROR] 記事取得失敗: {article['url']} -> {e}")
                    continue

            if not new_entries:
                print("[INFO] 追加する記事がありませんでした。")
                return

            updated = new_entries + existing

            if args.dry_run:
                print("=== Dry run 結果 ===")
                for e in new_entries:
                    print(f"  - {e['slug']}: {e['title'][:50]}")
                    print(f"    date: {e['date']}, area: {e['area']}")
                    print(f"    thumb: {e['thumbnail'][:60] if e['thumbnail'] else ''}")
            else:
                save_articles(updated)
                print(f"[OK] articles.json に {len(new_entries)}件 追加しました")

        finally:
            browser.close()

    print(f"=== 完了 ({datetime.now().isoformat()}) ===")


if __name__ == "__main__":
    main()
