#!/usr/bin/env python3
"""
ワクスト自動投稿スクリプト (auto_post.py) v2

龍太郎さん（ryu-1992）のワクスト公開記事一覧から最新記事を取得し、
無料部分（導入）を抽出してサイトの articles.json に追加する。
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
    """年齢確認モーダルを閉じる（複数パターンに対応）"""
    time.sleep(1)
    try:
        result = page.evaluate("""
            () => {
                const clicked = [];

                // 年齢確認の「はい」ボタンを探す
                const allElements = document.querySelectorAll('a, button, span, div');
                for (const el of allElements) {
                    const txt = (el.textContent || '').trim();
                    if (txt === 'はい') {
                        try {
                            el.click();
                            clicked.push('はい');
                            break;
                        } catch (e) {}
                    }
                }

                // cookie で年齢確認を回避
                document.cookie = 'age_check=1; path=/; domain=.wakust.com';
                document.cookie = 'adult_check=1; path=/; domain=.wakust.com';

                return clicked;
            }
        """)
        print(f"[DEBUG] モーダル処理: {result}")
    except Exception as e:
        print(f"[DEBUG] モーダル処理エラー（無視可）: {e}")


def fetch_article_list(page):
    """クリエイターページから記事一覧を取得"""
    print(f"[INFO] 記事一覧を取得: {USER_PAGE_URL}")

    # 事前にcookieをセット
    page.context.add_cookies([
        {"name": "age_check", "value": "1", "domain": ".wakust.com", "path": "/"},
        {"name": "adult_check", "value": "1", "domain": ".wakust.com", "path": "/"},
    ])

    page.goto(USER_PAGE_URL, wait_until="networkidle", timeout=60000)
    time.sleep(3)

    accept_age_modal(page)
    time.sleep(2)

    page_title = page.title()
    body_html_len = page.evaluate("() => document.body.innerHTML.length")
    print(f"[DEBUG] ページタイトル: {page_title}")
    print(f"[DEBUG] body HTML長: {body_html_len}")

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

                let thumbnail = '';
                const imgInLink = link.querySelector('img');
                if (imgInLink && imgInLink.src) {
                    thumbnail = imgInLink.src;
                } else {
                    const parent = link.parentElement;
                    if (parent) {
                        const img = parent.querySelector('img');
                        if (img && img.src) thumbnail = img.src;
                    }
                    if (!thumbnail && link.previousElementSibling) {
                        const prevImg = link.previousElementSibling.querySelector
                            ? link.previousElementSibling.querySelector('img') : null;
                        if (prevImg && prevImg.src) thumbnail = prevImg.src;
                    }
                }

                const absoluteUrl = href.startsWith('http') ? href : 'https://wakust.com' + href;

                results.push({
                    id: articleId,
                    url: absoluteUrl,
                    title: title,
                    thumbnail: thumbnail
                });
            }
            return results;
        }
    """)

    print(f"[INFO] 取得した記事数: {len(articles)}件")
    if articles:
        print(f"[DEBUG] 最初の記事: {articles[0].get('title', '')[:50]}")
        print(f"[DEBUG] サムネイル: {articles[0].get('thumbnail', '(なし)')}")
    return articles


def fetch_article_detail(page, article_url):
    """記事詳細ページから本文と日付、カテゴリーを取得"""
    print(f"[INFO] 記事詳細を取得: {article_url}")
    page.goto(article_url, wait_until="networkidle", timeout=60000)
    time.sleep(2)
    accept_age_modal(page)
    time.sleep(2)

    detail = page.evaluate("""
        () => {
            const titleEl = document.querySelector('h1');
            const title = titleEl ? titleEl.textContent.trim() : '';

            let dateStr = '';
            const bodyText = document.body.innerText || '';
            const dateMatch = bodyText.match(/(\\d{4})年(\\d{2})月(\\d{2})日/);
            if (dateMatch) {
                dateStr = dateMatch[1] + '-' + dateMatch[2] + '-' + dateMatch[3];
            }

            let area = '';
            const catLinks = document.querySelectorAll('a[href*="/post-category/"]');
            for (const el of catLinks) {
                const txt = el.textContent.trim();
                if (txt && txt.length < 20) {
                    area = txt;
                    break;
                }
            }

            let content = '';
            const mainText = bodyText;

            const purchaseIdx = mainText.indexOf('を購入する');
            if (purchaseIdx > 0) {
                content = mainText.substring(0, purchaseIdx);
            } else {
                const registerIdx = mainText.indexOf('購入するには');
                if (registerIdx > 0) {
                    content = mainText.substring(0, registerIdx);
                } else {
                    content = mainText.substring(0, 2000);
                }
            }

            const bodyStartMarkers = ['こんにちは', 'こんばんは', 'どうも', 'ども、',
                                       'はじめまして', 'はじめに', 'お疲れ'];
            let bodyStartIdx = -1;
            for (const marker of bodyStartMarkers) {
                const idx = content.indexOf(marker);
                if (idx >= 0 && (bodyStartIdx === -1 || idx < bodyStartIdx)) {
                    bodyStartIdx = idx;
                }
            }

            if (bodyStartIdx >= 0) {
                content = content.substring(bodyStartIdx);
            } else {
                const lines = content.split('\\n').map(l => l.trim()).filter(l => l);
                content = lines.slice(Math.min(8, Math.floor(lines.length / 3))).join('\\n');
            }

            return { title, dateStr, area, content };
        }
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


def build_article_entry(detail, article_url, article_id, thumbnail=""):
    content_truncated = truncate_content(detail["content"], EXCERPT_MAX_CHARS)
    return {
        "slug": slugify_from_id(article_id),
        "title": detail["title"],
        "date": detail["dateStr"] or datetime.now().strftime("%Y-%m-%d"),
        "area": detail["area"] or "",
        "excerpt": make_excerpt(detail["content"]),
        "content": content_to_html(content_truncated),
        "wakust_url": article_url,
        "thumbnail": thumbnail,
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
                        article.get("thumbnail", "")
                    )
                    new_entries.append(entry)
                    print(f"[OK] 記事追加: {entry['title'][:40]}... ({entry['date']}, {entry['area']})")
                    print(f"     サムネイル: {entry['thumbnail'] or '(なし)'}")
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
