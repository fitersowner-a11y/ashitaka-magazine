#!/usr/bin/env python3
"""
売れ筋記事取得スクリプト (fetch_bestsellers.py)

ワクストの売上額ランキング（72時間）からトップ9記事を取得し、
data/bestseller_articles.json に保存する。

auto_post.py の後に実行して、記事詳細ページへのリンクを
既存の articles.json のデータから参照する。
"""

import json
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

RANKING_URL = "https://wakust.com/user/ryu-1992/?sort=proc"
BESTSELLER_JSON = Path(__file__).parent / "data" / "bestseller_articles.json"
ARTICLES_JSON = Path(__file__).parent / "data" / "articles.json"
MAX_ITEMS = 9
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


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
            }
        """)
    except Exception:
        pass


def fetch_bestsellers():
    print(f"=== 売れ筋記事取得 開始 ({datetime.now().isoformat()}) ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale="ja-JP",
            viewport={"width": 1280, "height": 800},
        )
        context.add_cookies([
            {"name": "age_check", "value": "1", "domain": ".wakust.com", "path": "/"},
            {"name": "adult_check", "value": "1", "domain": ".wakust.com", "path": "/"},
        ])
        page = context.new_page()

        try:
            page.goto(RANKING_URL, wait_until="networkidle", timeout=60000)
            time.sleep(3)
            accept_age_modal(page)
            time.sleep(2)

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

                        // サムネイル: 親要素から画像を探す
                        let thumbnail = '';
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

                        // カテゴリーを探す（リンクの近くにある post-category リンク）
                        let area = '';
                        const grandParent = parent ? parent.parentElement : null;
                        if (grandParent) {
                            const catLink = grandParent.querySelector('a[href*="/post-category/"]');
                            if (catLink) area = catLink.textContent.trim();
                        }

                        const absoluteUrl = href.startsWith('http') ? href : 'https://wakust.com' + href;

                        results.push({
                            id: articleId,
                            slug: 'wakust-' + articleId,
                            url: absoluteUrl,
                            title: title,
                            thumbnail: thumbnail,
                            area: area,
                            wakust_url: absoluteUrl
                        });
                    }
                    return results;
                }
            """)

            print(f"[INFO] 取得した記事数: {len(articles)}件")

            # 最大9件に絞る
            bestsellers = articles[:MAX_ITEMS]

            # 既存の articles.json からサムネイル・日付を補完
            existing_articles = {}
            if ARTICLES_JSON.exists():
                with open(ARTICLES_JSON, "r", encoding="utf-8") as f:
                    for a in json.load(f):
                        existing_articles[a["slug"]] = a

            for bs in bestsellers:
                existing = existing_articles.get(bs["slug"])
                if existing:
                    if not bs.get("thumbnail") and existing.get("thumbnail"):
                        bs["thumbnail"] = existing["thumbnail"]
                    if not bs.get("area") and existing.get("area"):
                        bs["area"] = existing["area"]
                    bs["date"] = existing.get("date", "")
                    bs["excerpt"] = existing.get("excerpt", "")
                else:
                    bs["date"] = ""
                    bs["excerpt"] = ""

            # 保存
            BESTSELLER_JSON.parent.mkdir(parents=True, exist_ok=True)
            with open(BESTSELLER_JSON, "w", encoding="utf-8") as f:
                json.dump(bestsellers, f, ensure_ascii=False, indent=2)

            print(f"[OK] bestseller_articles.json に {len(bestsellers)}件 保存しました")
            for bs in bestsellers:
                print(f"  - {bs['title'][:50]}")

        finally:
            browser.close()

    print(f"=== 完了 ({datetime.now().isoformat()}) ===")


if __name__ == "__main__":
    fetch_bestsellers()
