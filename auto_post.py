#!/usr/bin/env python3
"""
ワクスト自動投稿スクリプト (auto_post.py) v3

v2からの修正:
- タイトル抽出: サイト全体の h1 ではなく記事タイトルに絞る
- カテゴリー抽出: サイドメニューを除外し、記事本体のカテゴリーを取得
- サムネイル抽出: 記事詳細ページから OG画像 を取得する方式に変更
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

USER_PAGE_URL = "https://wakust.com/user/ryu-1992/?sort=postd"
ARTICLES_JSON = Path(__file__).parent / "data" / "articles.json"
MAX_POSTS_PER_RUN = 3
EXCERPT_MAX_CHARS = 500
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# サイドメニューのカテゴリー（これを除外する）
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
    """年齢確認モーダルを閉じる"""
    time.sleep(1)
    try:
        page.evaluate("""
            () => {
                const allElements = document.querySelectorAll('a, button, span, div');
                for (const el of allElements) {
                    const txt = (el.textContent || '').trim();
                    if (txt === 'はい') {
                        try { el.click(); break; } catch (e) {}
                    }
                }
                document.cookie = 'age_check=1; path=/; domain=.wakust.com';
                document.cookie = 'adult_check=1; path=/; domain=.wakust.com';
            }
        """)
    except Exception:
        pass


def fetch_article_list(page):
    """クリエイターページから記事一覧を取得"""
    print(f"[INFO] 記事一覧を取得: {USER_PAGE_URL}")

    page.context.add_cookies([
        {"name": "age_check", "value": "1", "domain": ".wakust.com", "path": "/"},
        {"name": "adult_check", "value": "1", "domain": ".wakust.com", "path": "/"},
    ])

    page.goto(USER_PAGE_URL, wait_until="networkidle", timeout=60000)
    time.sleep(3)
    accept_age_modal(page)
    time.sleep(2)

    page_title = page.title()
    print(f"[DEBUG] ページタイトル: {page_title}")

    articles = page.evaluate("""
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

    print(f"[INFO] 取得した記事数: {len(articles)}件")
    if articles:
        print(f"[DEBUG] 最初の記事: {articles[0].get('title', '')[:50]}")
    return articles


def fetch_article_detail(page, article_url):
    """記事詳細ページから本文、日付、カテゴリー、サムネイルを取得"""
    print(f"[INFO] 記事詳細を取得: {article_url}")
    page.goto(article_url, wait_until="networkidle", timeout=60000)
    time.sleep(2)
    accept_age_modal(page)
    time.sleep(2)

    # サイドバーカテゴリーをPython側から渡す
    sidebar_cats = json.dumps(list(SIDEBAR_CATEGORIES), ensure_ascii=False)

    detail = page.evaluate(f"""
        () => {{
            const SIDEBAR_CATS = new Set({sidebar_cats});

            // === タイトル ===
            // og:title か、最後の h1（記事タイトルは通常ページ下部）
            let title = '';
            const ogTitle = document.querySelector('meta[property="og:title"]');
            if (ogTitle && ogTitle.content) {{
                title = ogTitle.content.trim();
            }}
            if (!title) {{
                const h1s = document.querySelectorAll('h1');
                // ロゴの「ワクスト」を除外して最も長いh1を採用
                for (const h1 of h1s) {{
                    const t = (h1.textContent || '').trim();
                    if (t && t !== 'ワクスト' && t.length > title.length) {{
                        title = t;
                    }}
                }}
            }}

            // === 日付 ===
            let dateStr = '';
            const bodyText = document.body.innerText || '';
            const dateMatch = bodyText.match(/(\\d{{4}})年(\\d{{2}})月(\\d{{2}})日/);
            if (dateMatch) {{
                dateStr = dateMatch[1] + '-' + dateMatch[2] + '-' + dateMatch[3];
            }}

            // === カテゴリー ===
            // 記事本体エリア（article, main, または .post_content）内のカテゴリーリンクを探す
            let area = '';
            const mainArea = document.querySelector('article') ||
                            document.querySelector('main') ||
                            document.querySelector('.post-content') ||
                            document.body;

            const catLinks = mainArea.querySelectorAll('a[href*="/post-category/"]');
            // 記事のパンくず/タグエリアから、サイドメニュー以外のカテゴリーを選ぶ
            for (const el of catLinks) {{
                const txt = el.textContent.trim();
                if (!txt || txt.length > 20) continue;
                // サイドメニューにあるカテゴリーはスキップ（最初に出現するのはサイドメニュー）
                // ただし、本文エリアの記事タグとしても出現する可能性があるので、
                // 親要素が nav や aside でなければ採用
                const parent = el.closest('nav, aside, .sidebar, header');
                if (parent) continue;

                area = txt;
                break;
            }}

            // フォールバック: 全カテゴリーから、サイドメニューに固有なものを除外
            if (!area) {{
                const allCatLinks = document.querySelectorAll('a[href*="/post-category/"]');
                for (const el of allCatLinks) {{
                    const txt = el.textContent.trim();
                    if (!txt || txt.length > 20) continue;
                    // 記事で最もありうるカテゴリー（東京都、神奈川、多摩、新宿、池袋など）
                    const likelyAreas = ['東京都', '神奈川県', '埼玉県', '千葉県', '多摩',
                                          '新宿', '池袋', '愛知県', '大阪府', '兵庫県',
                                          '福岡県', 'ノウハウ(ネット)', 'ノウハウ(リアル)'];
                    if (likelyAreas.includes(txt)) {{
                        area = txt;
                        break;
                    }}
                }}
            }}

            // === サムネイル ===
            let thumbnail = '';
            const ogImage = document.querySelector('meta[property="og:image"]');
            if (ogImage && ogImage.content) {{
                thumbnail = ogImage.content;
            }}
            // フォールバック: 記事エリア内の最初の画像
            if (!thumbnail) {{
                const articleImg = mainArea.querySelector('img[src*="wp-content/uploads"]');
                if (articleImg && articleImg.src) {{
                    thumbnail = articleImg.src;
                }}
            }}

            // === 本文 ===
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
            articles = fetch_article_list(page)
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
            for article in to_post:
                try:
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
                    print(f"    thumb: {e['thumbnail']}")
                    print(f"    excerpt: {e['excerpt'][:80]}...")
            else:
                save_articles(updated)
                print(f"[OK] articles.json に {len(new_entries)}件 追加しました")

        finally:
            browser.close()

    print(f"=== 完了 ({datetime.now().isoformat()}) ===")


if __name__ == "__main__":
    main()
