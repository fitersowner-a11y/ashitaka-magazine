#!/usr/bin/env python3
"""
ワクスト自動投稿スクリプト (auto_post.py)

龍太郎さん（ryu-1992）のワクスト公開記事一覧から最新記事を取得し、
無料部分（導入）を抽出してサイトの articles.json に追加する。

動作フロー:
1. https://wakust.com/user/ryu-1992/?sort=postd から最新記事一覧を取得
2. 既に articles.json に登録済みの記事はスキップ
3. 未登録の記事を最大N件、詳細ページから本文を取得
4. 本文の無料部分を抽出して articles.json に追加
5. 変更があればGitコミット→pushで自動デプロイ

使い方:
  python3 auto_post.py            # 本番実行
  python3 auto_post.py --dry-run  # 追加内容の確認のみ
  python3 auto_post.py --max 3    # 最大投稿数を指定（デフォルト3）
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

# 設定
USER_PAGE_URL = "https://wakust.com/user/ryu-1992/?sort=postd"
ARTICLES_JSON = Path(__file__).parent / "data" / "articles.json"
WAKUST_USER_URL = "https://wakust.com/user/ryu-1992/"
MAX_POSTS_PER_RUN = 3  # 1回の実行で投稿する最大記事数
EXCERPT_MAX_CHARS = 500  # サイトに載せる無料部分の最大文字数
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def load_articles():
    """既存の記事データを読み込む"""
    if not ARTICLES_JSON.exists():
        return []
    with open(ARTICLES_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def save_articles(articles):
    """記事データを保存する"""
    ARTICLES_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(ARTICLES_JSON, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)


def accept_age_modal(page):
    """年齢確認モーダルを閉じる"""
    try:
        page.evaluate("""
            () => {
                const links = document.querySelectorAll('a, button');
                for (const link of links) {
                    const txt = (link.textContent || '').trim();
                    if (txt === 'はい') {
                        link.click();
                        return true;
                    }
                }
                return false;
            }
        """)
    except Exception:
        pass


def fetch_article_list(page):
    """クリエイターページから記事一覧を取得"""
    print(f"[INFO] 記事一覧を取得: {USER_PAGE_URL}")
    page.goto(USER_PAGE_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    accept_age_modal(page)
    time.sleep(1)

    # 記事カードを取得
    articles = page.evaluate("""
        () => {
            const results = [];
            // 記事カードのリンクを抽出
            const links = document.querySelectorAll('a[href*="/ryu-1992/"]');
            const seen = new Set();

            for (const link of links) {
                const href = link.getAttribute('href');
                // 記事詳細URLのパターン: /ryu-1992/数字/
                const match = href.match(/\\/ryu-1992\\/(\\d+)\\/?$/);
                if (!match) continue;

                const articleId = match[1];
                if (seen.has(articleId)) continue;
                seen.add(articleId);

                // タイトルテキストを持つリンクだけを対象にする（サムネイルリンクはスキップ）
                const title = (link.textContent || '').trim();
                if (!title || title.length < 5) continue;

                // 画像URLを探す (兄弟要素・親要素から)
                let thumbnail = '';
                const img = link.querySelector('img') ||
                           (link.previousElementSibling && link.previousElementSibling.querySelector('img')) ||
                           (link.parentElement && link.parentElement.querySelector('img'));
                if (img) thumbnail = img.src || '';

                results.push({
                    id: articleId,
                    url: href.startsWith('http') ? href : 'https://wakust.com' + href,
                    title: title,
                    thumbnail: thumbnail
                });
            }
            return results;
        }
    """)

    print(f"[INFO] 取得した記事数: {len(articles)}件")
    return articles


def fetch_article_detail(page, article_url):
    """記事詳細ページから本文と日付、カテゴリーを取得"""
    print(f"[INFO] 記事詳細を取得: {article_url}")
    page.goto(article_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    accept_age_modal(page)
    time.sleep(1)

    detail = page.evaluate("""
        () => {
            // タイトル
            const titleEl = document.querySelector('h1');
            const title = titleEl ? titleEl.textContent.trim() : '';

            // 投稿日（タイトル下の日付を探す）
            let dateStr = '';
            const bodyText = document.body.innerText;
            const dateMatch = bodyText.match(/(\\d{4})年(\\d{2})月(\\d{2})日/);
            if (dateMatch) {
                dateStr = dateMatch[1] + '-' + dateMatch[2] + '-' + dateMatch[3];
            }

            // カテゴリー（パンくずリストまたは記事内のカテゴリータグ）
            let area = '';
            const catLinks = document.querySelectorAll('a[href*="/post-category/"]');
            for (const el of catLinks) {
                const txt = el.textContent.trim();
                if (txt) {
                    area = txt;
                    break;
                }
            }

            // 本文（無料部分のみ）
            // 「購入する」「購入」というキーワードで切り取る
            let content = '';
            // まずメインコンテンツエリアを特定
            const mainArticle = document.querySelector('article') || document.querySelector('main') || document.body;
            const mainText = mainArticle.innerText || '';

            // 「を購入する」という見出しの手前までが無料部分
            const purchaseIdx = mainText.indexOf('を購入する');
            if (purchaseIdx > 0) {
                content = mainText.substring(0, purchaseIdx);
            } else {
                // フォールバック: 「購入するには」の手前まで
                const registerIdx = mainText.indexOf('購入するにはワクスト');
                if (registerIdx > 0) {
                    content = mainText.substring(0, registerIdx);
                } else {
                    content = mainText.substring(0, 2000);
                }
            }

            // 本文からタイトル・日付・カテゴリー・プロフィール部分を除去
            // タイトル、ユーザー名、日付行、カテゴリー行をスキップ
            const lines = content.split('\\n').map(l => l.trim()).filter(l => l);
            const bodyStartMarkers = ['こんにちは', 'どうも', 'ども、', 'はじめまして', 'はじめに'];
            let bodyStartIdx = -1;
            for (let i = 0; i < lines.length; i++) {
                for (const marker of bodyStartMarkers) {
                    if (lines[i].startsWith(marker)) {
                        bodyStartIdx = i;
                        break;
                    }
                }
                if (bodyStartIdx >= 0) break;
            }

            if (bodyStartIdx >= 0) {
                content = lines.slice(bodyStartIdx).join('\\n\\n');
            } else {
                // マーカーが見つからない場合、最初の10行をスキップ（メタ情報のため）
                content = lines.slice(Math.min(10, Math.floor(lines.length / 3))).join('\\n\\n');
            }

            return { title, dateStr, area, content };
        }
    """)

    return detail


def slugify_from_id(article_id):
    """記事IDからslugを生成"""
    return f"wakust-{article_id}"


def truncate_content(content, max_chars=EXCERPT_MAX_CHARS):
    """本文を指定文字数で切る。句点で自然に区切る"""
    if len(content) <= max_chars:
        return content

    truncated = content[:max_chars]
    # 最後の句点で切る
    last_period = truncated.rfind("。")
    if last_period > max_chars * 0.5:
        truncated = truncated[:last_period + 1]
    return truncated


def make_excerpt(content, max_chars=100):
    """サイトのカード表示用の短い要約を作る"""
    # 最初の段落を取り出す
    first_para = content.split("\n")[0] if "\n" in content else content[:200]
    return truncate_content(first_para, max_chars)


def content_to_html(content):
    """プレーンテキストをHTMLに変換（段落分け）"""
    paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
    return "\n".join(f"<p>{p}</p>" for p in paragraphs)


def build_article_entry(detail, article_url, article_id, thumbnail=""):
    """articles.json の形式に変換"""
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

    # 既存記事を読み込み
    existing = load_articles()
    existing_ids = {
        art["slug"].replace("wakust-", "")
        for art in existing
        if art["slug"].startswith("wakust-")
    }
    print(f"既存の記事数: {len(existing)} (ワクスト由来: {len(existing_ids)})")

    # Playwright起動
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=DEFAULT_USER_AGENT, locale="ja-JP")
        page = context.new_page()

        try:
            # 記事一覧取得
            articles = fetch_article_list(page)
            if not articles:
                print("[WARN] 記事が取得できませんでした。終了します。")
                return

            # 未登録の記事をフィルタリング
            new_articles = [a for a in articles if a["id"] not in existing_ids]
            print(f"[INFO] 未登録の記事: {len(new_articles)}件")

            if not new_articles:
                print("[INFO] 新しい記事はありません。終了します。")
                return

            # 最大N件までに絞る
            to_post = new_articles[: args.max]
            print(f"[INFO] 今回投稿する記事: {len(to_post)}件")

            # 各記事の詳細を取得
            new_entries = []
            for article in to_post:
                try:
                    detail = fetch_article_detail(page, article["url"])
                    if not detail["content"] or len(detail["content"]) < 50:
                        print(f"[WARN] 本文が取得できませんでした: {article['url']}")
                        continue

                    entry = build_article_entry(
                        detail, article["url"], article["id"], article.get("thumbnail", "")
                    )
                    new_entries.append(entry)
                    print(f"[OK] 記事追加: {entry['title']}")
                    time.sleep(2)  # サーバー負荷軽減
                except Exception as e:
                    print(f"[ERROR] 記事取得失敗: {article['url']} -> {e}")
                    continue

            if not new_entries:
                print("[INFO] 追加する記事がありませんでした。")
                return

            # articles.json に追加（新しい記事を先頭に）
            updated = new_entries + existing

            if args.dry_run:
                print("=== Dry run 結果 ===")
                for e in new_entries:
                    print(f"  - {e['slug']}: {e['title']} ({e['date']}, {e['area']})")
                    print(f"    excerpt: {e['excerpt'][:80]}...")
            else:
                save_articles(updated)
                print(f"[OK] articles.json に {len(new_entries)}件 追加しました")

        finally:
            browser.close()

    print(f"=== 完了 ({datetime.now().isoformat()}) ===")


if __name__ == "__main__":
    main()
