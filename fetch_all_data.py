#!/usr/bin/env python3
"""
ワクスト全記事データ取得スクリプト (fetch_all_data.py) v3

ログインして管理画面から全記事の詳細データを取得し、
data/all_articles_data.json に保存する。
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
    time.sleep(3)
    accept_age_modal(page)
    time.sleep(2)

    # メールアドレス入力
    email_filled = page.evaluate(f"""
        () => {{
            const email = {json.dumps(WAKUST_EMAIL)};
            const el = document.querySelector('input[name="login_email"]');
            if (el) {{
                el.value = email;
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }}
            return false;
        }}
    """)
    print(f"[DEBUG] メールアドレス入力: {email_filled}")

    # パスワード入力
    pw_filled = page.evaluate(f"""
        () => {{
            const pw = {json.dumps(WAKUST_PASSWORD)};
            const el = document.querySelector('input[name="login_password"]');
            if (el) {{
                el.value = pw;
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }}
            return false;
        }}
    """)
    print(f"[DEBUG] パスワード入力: {pw_filled}")

    if not email_filled or not pw_filled:
        print("[ERROR] ログインフォームが見つかりません")
        return False

    # ログインボタンをクリック
    page.evaluate("""
        () => {
            // login_submit クラスのボタンを探す
            const submitBtn = document.querySelector('.login_submit');
            if (submitBtn) { submitBtn.click(); return true; }

            // フォールバック
            const candidates = document.querySelectorAll('input[type="submit"], button[type="submit"], button');
            for (const btn of candidates) {
                const txt = (btn.value || btn.textContent || '').trim();
                if (txt === 'ログイン' || txt === 'Login') {
                    btn.click();
                    return true;
                }
            }
            return false;
        }
    """)

    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(3)
    accept_age_modal(page)
    time.sleep(1)

    # ログイン確認
    current_url = page.url
    print(f"[DEBUG] ログイン後URL: {current_url}")

    if "login" in current_url.lower() and "mypage" not in current_url.lower():
        page_text = page.evaluate("() => document.body.innerText.substring(0, 300)")
        print(f"[DEBUG] ページ冒頭: {page_text[:150]}")
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

    if page_num == 1:
        debug_info = page.evaluate("""
            () => {
                const rows = document.querySelectorAll('tr');
                const info = { total_rows: rows.length, sample_cells: [] };
                if (rows.length > 1) {
                    const cells = rows[1].querySelectorAll('td');
                    info.sample_cells = Array.from(cells).map((c, i) => ({
                        index: i,
                        text: c.textContent.trim().substring(0, 50),
                        hasLink: !!c.querySelector('a'),
                        hasImg: !!c.querySelector('img')
                    }));
                }
                return info;
            }
        """)
        print(f"[DEBUG] テーブル構造: 行数={debug_info['total_rows']}")
        for cell in debug_info.get("sample_cells", []):
            print(f"[DEBUG]   td[{cell['index']}]: {cell['text'][:40]}... link={cell['hasLink']} img={cell['hasImg']}")

    articles = page.evaluate("""
        () => {
            const results = [];
            const rows = document.querySelectorAll('tr');

            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                if (cells.length < 5) continue;

                let articleId = '';
                let title = '';
                let editUrl = '';

                const allLinks = row.querySelectorAll('a[href]');
                for (const link of allLinks) {
                    const href = link.getAttribute('href') || '';
                    const publicMatch = href.match(/\\/ryu-1992\\/(\\d{4,})\\/?/);
                    if (publicMatch && !articleId) {
                        articleId = publicMatch[1];
                        const linkText = link.textContent.trim();
                        if (linkText.length > 5) title = linkText;
                    }
                    const editMatch = href.match(/post_id=(\\d+)/) || href.match(/p=(\\d+)/);
                    if (editMatch && !articleId) {
                        articleId = editMatch[1];
                    }
                    if (href.includes('post_edit') || href.includes('action=edit')) {
                        editUrl = href.startsWith('http') ? href : 'https://wakust.com' + href;
                    }
                }

                if (!articleId) continue;
                if (!title) {
                    for (const cell of cells) {
                        const t = cell.textContent.trim();
                        if (t.length > 10 && !t.includes('販売') && !t.includes('pt')) {
                            title = t.split('\\n')[0].trim();
                            break;
                        }
                    }
                }

                const img = row.querySelector('img');
                const thumbnail = img ? (img.src || '') : '';

                const fullText = row.textContent;

                let category = '';
                const catLink = row.querySelector('a[href*="/post-category/"]');
                if (catLink) category = catLink.textContent.trim();
                if (!category) {
                    const areas = ['東京都', '神奈川県', '埼玉県', '千葉県', '新宿', '池袋', '多摩',
                                   '愛知県', '大阪府', '兵庫県', '福岡県', 'ノウハウ(ネット)', 'ノウハウ(リアル)'];
                    for (const a of areas) {
                        if (fullText.includes(a)) { category = a; break; }
                    }
                }

                const priceMatch = fullText.match(/([\\d,]+)\\s*pt/);
                const price = priceMatch ? parseInt(priceMatch[1].replace(/,/g, '')) : 0;

                const pvMatch = fullText.match(/全期間\\s*[:：]\\s*([\\d,]+)/);
                const pvTotal = pvMatch ? parseInt(pvMatch[1].replace(/,/g, '')) : 0;

                const salesCountMatch = fullText.match(/販売回数\\s*[:：]\\s*([\\d,]+)/);
                const salesCount = salesCountMatch ? parseInt(salesCountMatch[1].replace(/,/g, '')) : 0;

                const salesAmountMatch = fullText.match(/売上\\s*[:：]\\s*([\\d,]+)\\s*pt/);
                const salesAmount = salesAmountMatch ? parseInt(salesAmountMatch[1].replace(/,/g, '')) : 0;

                const dateMatch = fullText.match(/(\\d{4})-(\\d{2})-(\\d{2})/);
                const postDate = dateMatch ? dateMatch[0] : '';

                results.push({
                    id: articleId,
                    title: title.substring(0, 200),
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
    if articles:
        print(f"[DEBUG] 最初の記事: {articles[0]['title'][:40]} (ID:{articles[0]['id']}, 売上:{articles[0]['sales_amount']}pt)")
    return articles


def fetch_article_content(page, article):
    """記事の公開ページから無料本文を、編集ページから有料本文を取得"""
    public_url = article["wakust_url"]
    edit_url = article.get("edit_url", "")

    print(f"[INFO]   公開ページから無料本文取得...")
    page.goto(public_url, wait_until="networkidle", timeout=60000)
    time.sleep(2)
    accept_age_modal(page)
    time.sleep(1)

    free_result = page.evaluate("""
        () => {
            const bodyText = document.body.innerText || '';
            const purchaseIdx = bodyText.indexOf('を購入する');
            let content = '';
            if (purchaseIdx > 0) {
                content = bodyText.substring(0, purchaseIdx);
            } else {
                const registerIdx = bodyText.indexOf('購入するには');
                content = registerIdx > 0 ? bodyText.substring(0, registerIdx) : bodyText.substring(0, 3000);
            }

            const markers = ['こんにちは', 'こんばんは', 'どうも', 'ども、', 'はじめまして', 'はじめに', 'お疲れ'];
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

            let thumbnail = '';
            const ogImage = document.querySelector('meta[property="og:image"]');
            if (ogImage && ogImage.content) thumbnail = ogImage.content;

            return { free_content: content, thumbnail: thumbnail };
        }
    """)

    paid_content = ""
    if edit_url:
        print(f"[INFO]   編集ページから有料本文取得...")
        page.goto(edit_url, wait_until="networkidle", timeout=60000)
        time.sleep(3)
        accept_age_modal(page)
        time.sleep(2)

        for attempt in range(5):
            paid_content = page.evaluate("""
                () => {
                    if (typeof tinymce !== 'undefined' && tinymce.editors && tinymce.editors.length > 0) {
                        for (const editor of tinymce.editors) {
                            const content = editor.getContent();
                            if (content && content.length > 10) return content;
                        }
                    }
                    const iframes = document.querySelectorAll('iframe');
                    for (const iframe of iframes) {
                        try {
                            const body = iframe.contentDocument.querySelector('body.mce-content-body');
                            if (body && body.innerHTML && body.innerHTML.length > 10) return body.innerHTML;
                        } catch (e) {}
                    }
                    return '';
                }
            """)
            if paid_content and len(paid_content) > 10:
                break
            print(f"[INFO]   TinyMCE待機中... ({attempt + 1}/5)")
            time.sleep(3)

    return {
        "free_content": free_result.get("free_content", ""),
        "paid_content": paid_content,
        "thumbnail": free_result.get("thumbnail", "") or article.get("thumbnail", ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-content", action="store_true", help="一覧データのみ取得")
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
            if not login(page):
                print("[ERROR] ログイン失敗。終了します。")
                return

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

                has_next = page.evaluate("""
                    () => {
                        const links = document.querySelectorAll('a[href]');
                        for (const link of links) {
                            const text = (link.textContent || '').trim();
                            if (text === '>' || text === '›' || text === '次' || text === '»') return true;
                        }
                        return false;
                    }
                """)
                if not has_next:
                    print("[INFO] 最終ページに到達")
                    break
                time.sleep(2)

            print(f"\n[INFO] 全記事数: {len(all_articles)}件")

            if not args.skip_content:
                print("\n--- STEP 2: 記事本文取得 ---")
                targets = []
                for aid, article in all_articles.items():
                    if args.update_only:
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

            save_data(all_articles)
            print(f"\n[OK] all_articles_data.json に {len(all_articles)}件 保存しました")

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
