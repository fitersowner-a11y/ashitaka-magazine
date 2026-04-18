#!/usr/bin/env python3
"""
ワクスト全記事データ取得スクリプト (fetch_all_data.py)

ログインして管理画面から全記事の詳細データを取得し、
data/all_articles_data.json に保存する。

取得するデータ:
- 記事ID, タイトル, カテゴリー, 価格
- 販売回数, 売上pt, PV
- 投稿日時, サムネイル
- 無料本文, 有料本文（編集ページから取得）

使い方:
  python3 fetch_all_data.py                  # 全記事取得
  python3 fetch_all_data.py --skip-content   # 一覧データのみ（本文取得スキップ）
  python3 fetch_all_data.py --update-only    # 新規・未取得の記事のみ本文取得
"""

import json
import os
import re
import time
import argparse
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

POST_LIST_URL = "https://wakust.com/mypage/?post_list"
LOGIN_URL = "https://wakust.com/login/"
ALL_DATA_JSON = Path(__file__).parent / "data" / "all_articles_data.json"
MAX_PAGES = 10

WAKUST_EMAIL = os.environ.get("WAKUST_EMAIL", "")
WAKUST_PASSWORD = os.environ.get("WAKUST_PASSWORD", "")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def load_existing_data():
    if not ALL_DATA_JSON.exists():
        return {}
    with open(ALL_DATA_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {a["id"]: a for a in data}


def save_data(articles_dict):
    ALL_DATA_JSON.parent.mkdir(parents=True, exist_ok=True)
    articles_list = sorted(articles_dict.values(), key=lambda a: a.get("post_date", ""), reverse=True)
    with open(ALL_DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(articles_list, f, ensure_ascii=False, indent=2)


def accept_age_modal(page):
    time.sleep(1)
    try:
        page.evaluate("""
            () => {
                const els = document.querySelectorAll('a, button, span, div');
                for (const el of els) {
                    if ((el.textContent || '').trim() === 'はい') {
                        try { el.click(); break; } catch (e) {}
                    }
                }
            }
        """)
    except Exception:
        pass


def login(page):
    """ワクストにログイン"""
    print("[INFO] ログイン中...")
    page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
    time.sleep(2)
    accept_age_modal(page)
    time.sleep(1)

    page.fill('input[name="user_login"], input[type="text"], input[name="log"]', WAKUST_EMAIL)
    page.fill('input[name="user_pass"], input[type="password"], input[name="pwd"]', WAKUST_PASSWORD)

    # ログインボタンをクリック
    page.evaluate("""
        () => {
            const buttons = document.querySelectorAll('input[type="submit"], button[type="submit"], button');
            for (const btn of buttons) {
                const txt = (btn.value || btn.textContent || '').trim();
                if (txt === 'ログイン' || txt === 'Login' || txt === 'ログインする') {
                    btn.click();
                    return true;
                }
            }
            // フォーム送信のフォールバック
            const form = document.querySelector('form');
            if (form) { form.submit(); return true; }
            return false;
        }
    """)

    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(3)
    accept_age_modal(page)

    # ログイン確認
    current_url = page.url
    if "login" in current_url.lower():
        print("[ERROR] ログインに失敗した可能性があります")
        return False

    print("[OK] ログイン成功")
    return True


def fetch_list_page(page, page_num):
    """管理画面の記事一覧から1ページ分のデータを取得"""
    if page_num == 1:
        url = POST_LIST_URL
    else:
        url = f"{POST_LIST_URL}&paged={page_num}"

    print(f"[INFO] 一覧ページ {page_num} を取得: {url}")
    page.goto(url, wait_until="networkidle", timeout=60000)
    time.sleep(2)
    accept_age_modal(page)
    time.sleep(1)

    articles = page.evaluate("""
        () => {
            const results = [];
            // テーブルの行を取得
            const rows = document.querySelectorAll('table tr, .post_list_table tr');

            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                if (cells.length < 6) continue;

                // タイトルからリンクを取得
                const titleCell = cells[1] || cells[0];
                const titleLink = titleCell ? titleCell.querySelector('a[href]') : null;
                if (!titleLink) continue;

                const href = titleLink.getAttribute('href') || '';
                // 記事URLまたは編集URLからIDを抽出
                let articleId = '';
                const idMatch = href.match(/\\/(\\d{4,})\\/?(?:\\?|$)/) ||
                               href.match(/post_id=(\\d+)/) ||
                               href.match(/p=(\\d+)/);
                if (idMatch) articleId = idMatch[1];
                if (!articleId) continue;

                const title = (titleLink.textContent || '').trim();

                // 画像
                const imgCell = cells[0];
                const img = imgCell ? imgCell.querySelector('img') : null;
                const thumbnail = img ? (img.src || '') : '';

                // カテゴリー
                const catCell = cells[2];
                const category = catCell ? catCell.textContent.trim() : '';

                // 販売pt（価格）
                const priceCell = cells[3];
                const priceText = priceCell ? priceCell.textContent.trim() : '';
                const priceMatch = priceText.match(/([\\d,]+)\\s*pt/);
                const price = priceMatch ? parseInt(priceMatch[1].replace(/,/g, '')) : 0;

                // PV
                const pvCell = cells[4];
                const pvText = pvCell ? pvCell.textContent.trim() : '';
                const pvTotalMatch = pvText.match(/全期間\\s*[:：]\\s*([\\d,]+)/);
                const pvTotal = pvTotalMatch ? parseInt(pvTotalMatch[1].replace(/,/g, '')) : 0;

                // 売上情報
                const salesCell = cells[5];
                const salesText = salesCell ? salesCell.textContent.trim() : '';
                const salesCountMatch = salesText.match(/販売回数\\s*[:：]\\s*([\\d,]+)/);
                const salesAmountMatch = salesText.match(/売上\\s*[:：]\\s*([\\d,]+)\\s*pt/);
                const salesCount = salesCountMatch ? parseInt(salesCountMatch[1].replace(/,/g, '')) : 0;
                const salesAmount = salesAmountMatch ? parseInt(salesAmountMatch[1].replace(/,/g, '')) : 0;

                // 投稿日時
                const dateCell = cells[cells.length - 3] || cells[7];
                const dateText = dateCell ? dateCell.textContent.trim() : '';
                const dateMatch = dateText.match(/(\\d{4})-(\\d{2})-(\\d{2})/);
                const postDate = dateMatch ? dateMatch[0] : '';

                // 編集リンクを探す
                let editUrl = '';
                const allLinks = row.querySelectorAll('a[href]');
                for (const link of allLinks) {
                    const h = link.getAttribute('href') || '';
                    if (h.includes('post_edit') || h.includes('action=edit')) {
                        editUrl = h.startsWith('http') ? h : 'https://wakust.com' + h;
                        break;
                    }
                }

                results.push({
                    id: articleId,
                    title: title,
                    category: category,
                    price: price,
                    pv_total: pvTotal,
                    sales_count: salesCount,
                    sales_amount: salesAmount,
                    post_date: postDate,
                    thumbnail: thumbnail,
                    edit_url: editUrl,
                    wakust_url: 'https://wakust.com/ryu-1992/' + articleId + '/'
                });
            }
            return results;
        }
    """)

    print(f"[INFO] ページ {page_num}: {len(articles)}件取得")
    return articles


def fetch_article_content(page, article):
    """記事の公開ページから無料本文を、編集ページから有料本文を取得"""
    article_id = article["id"]
    public_url = article["wakust_url"]
    edit_url = article.get("edit_url", "")

    # === 公開ページから無料本文を取得 ===
    print(f"[INFO]   公開ページから無料本文取得: {public_url}")
    page.goto(public_url, wait_until="networkidle", timeout=60000)
    time.sleep(2)
    accept_age_modal(page)
    time.sleep(1)

    free_content = page.evaluate("""
        () => {
            const bodyText = document.body.innerText || '';

            // 「を購入する」の手前が無料部分
            const purchaseIdx = bodyText.indexOf('を購入する');
            let content = '';
            if (purchaseIdx > 0) {
                content = bodyText.substring(0, purchaseIdx);
            } else {
                const registerIdx = bodyText.indexOf('購入するには');
                if (registerIdx > 0) {
                    content = bodyText.substring(0, registerIdx);
                } else {
                    content = bodyText.substring(0, 3000);
                }
            }

            // 本文開始位置を特定
            const markers = ['こんにちは', 'こんばんは', 'どうも', 'ども、',
                            'はじめまして', 'はじめに', 'お疲れ'];
            let startIdx = -1;
            for (const m of markers) {
                const idx = content.indexOf(m);
                if (idx >= 0 && (startIdx === -1 || idx < startIdx)) startIdx = idx;
            }

            if (startIdx >= 0) {
                content = content.substring(startIdx);
            } else {
                const lines = content.split('\\n').map(l => l.trim()).filter(l => l);
                content = lines.slice(Math.min(8, Math.floor(lines.length / 3))).join('\\n');
            }

            // サムネイル（og:image）
            let thumbnail = '';
            const ogImage = document.querySelector('meta[property="og:image"]');
            if (ogImage && ogImage.content) thumbnail = ogImage.content;

            return { free_content: content, thumbnail: thumbnail };
        }
    """)

    # === 編集ページから有料本文を取得 ===
    paid_content = ""
    if edit_url:
        print(f"[INFO]   編集ページから有料本文取得...")
        page.goto(edit_url, wait_until="networkidle", timeout=60000)
        time.sleep(3)
        accept_age_modal(page)
        time.sleep(2)

        # TinyMCEの読み込みを待つ（リトライ）
        for attempt in range(5):
            paid_content = page.evaluate("""
                () => {
                    // TinyMCE APIから取得を試みる
                    if (typeof tinymce !== 'undefined' && tinymce.editors && tinymce.editors.length > 0) {
                        for (const editor of tinymce.editors) {
                            const content = editor.getContent();
                            if (content && content.length > 10) {
                                return content;
                            }
                        }
                    }

                    // iframe内のbodyから直接取得
                    const iframes = document.querySelectorAll('iframe');
                    for (const iframe of iframes) {
                        try {
                            const body = iframe.contentDocument.querySelector('body.mce-content-body');
                            if (body && body.innerHTML && body.innerHTML.length > 10) {
                                return body.innerHTML;
                            }
                        } catch (e) {}
                    }

                    return '';
                }
            """)

            if paid_content and len(paid_content) > 10:
                break
            print(f"[INFO]   TinyMCE待機中... (attempt {attempt + 1}/5)")
            time.sleep(3)

    return {
        "free_content": free_content.get("free_content", ""),
        "paid_content": paid_content,
        "thumbnail": free_content.get("thumbnail", "") or article.get("thumbnail", ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-content", action="store_true", help="一覧データのみ取得（本文スキップ）")
    parser.add_argument("--update-only", action="store_true", help="未取得の記事のみ本文取得")
    args = parser.parse_args()

    if not WAKUST_EMAIL or not WAKUST_PASSWORD:
        print("[ERROR] WAKUST_EMAIL と WAKUST_PASSWORD を環境変数に設定してください")
        return

    print(f"=== 全記事データ取得 開始 ({datetime.now().isoformat()}) ===")
    print(f"本文取得: {'スキップ' if args.skip_content else '更新のみ' if args.update_only else '全記事'}")

    existing_data = load_existing_data()
    print(f"既存データ: {len(existing_data)}件")

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
            # ログイン
            if not login(page):
                print("[ERROR] ログイン失敗。終了します。")
                return

            # === STEP 1: 一覧ページから全記事メタデータ取得 ===
            print("\n--- STEP 1: 記事一覧取得 ---")
            all_articles = {}

            for page_num in range(1, MAX_PAGES + 1):
                articles = fetch_list_page(page, page_num)
                if not articles:
                    print(f"[INFO] ページ {page_num} に記事なし。巡回終了")
                    break

                for a in articles:
                    aid = a["id"]
                    if aid in existing_data:
                        # 既存データのメタ情報を更新（売上等は変動する）
                        existing_data[aid].update({
                            "price": a["price"],
                            "pv_total": a["pv_total"],
                            "sales_count": a["sales_count"],
                            "sales_amount": a["sales_amount"],
                        })
                        all_articles[aid] = existing_data[aid]
                    else:
                        all_articles[aid] = a
                        all_articles[aid]["free_content"] = ""
                        all_articles[aid]["paid_content"] = ""

                # 次のページがあるか
                has_next = page.evaluate("""
                    () => {
                        const links = document.querySelectorAll('a[href]');
                        for (const link of links) {
                            const text = (link.textContent || '').trim();
                            if (text === '>' || text === '›' || text === '次' || text === '次へ' || text === '»') {
                                return true;
                            }
                        }
                        return false;
                    }
                """)

                if not has_next:
                    print(f"[INFO] 最終ページに到達")
                    break

                time.sleep(2)

            print(f"\n[INFO] 全記事数: {len(all_articles)}件")

            # === STEP 2: 各記事の本文取得 ===
            if not args.skip_content:
                print("\n--- STEP 2: 記事本文取得 ---")

                targets = []
                for aid, article in all_articles.items():
                    if args.update_only:
                        # 本文が未取得の記事のみ
                        if not article.get("free_content") and not article.get("paid_content"):
                            targets.append(article)
                    else:
                        targets.append(article)

                print(f"[INFO] 本文取得対象: {len(targets)}件")

                for i, article in enumerate(targets):
                    try:
                        print(f"\n[INFO] ({i+1}/{len(targets)}) {article['title'][:40]}...")
                        content = fetch_article_content(page, article)
                        article["free_content"] = content["free_content"]
                        article["paid_content"] = content["paid_content"]
                        if content["thumbnail"]:
                            article["thumbnail"] = content["thumbnail"]
                        print(f"[OK]   無料: {len(article['free_content'])}文字, 有料: {len(article['paid_content'])}文字")
                        time.sleep(2)
                    except Exception as e:
                        print(f"[ERROR] 本文取得失敗: {article.get('title', '')[:30]} -> {e}")
                        continue

            # 保存
            save_data(all_articles)
            print(f"\n[OK] all_articles_data.json に {len(all_articles)}件 保存しました")

            # サマリー表示
            with_paid = sum(1 for a in all_articles.values() if a.get("paid_content"))
            with_free = sum(1 for a in all_articles.values() if a.get("free_content"))
            total_sales = sum(a.get("sales_amount", 0) for a in all_articles.values())
            print(f"\n=== サマリー ===")
            print(f"  記事数: {len(all_articles)}")
            print(f"  無料本文取得済み: {with_free}件")
            print(f"  有料本文取得済み: {with_paid}件")
            print(f"  総売上: {total_sales:,}pt")

        finally:
            browser.close()

    print(f"\n=== 完了 ({datetime.now().isoformat()}) ===")


if __name__ == "__main__":
    main()
