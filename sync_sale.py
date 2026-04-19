#!/usr/bin/env python3
"""
セール記事連携スクリプト (sync_sale.py)

wakust-auto-sale リポジトリの sale_state.json を取得し、
ashitaka-magazine の data/sale_articles.json に変換して保存する。

GitHub APIを使ってPublicリポジトリからファイルを取得するため、
認証は不要。
"""

import json
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

SALE_STATE_URL = "https://raw.githubusercontent.com/fitersowner-a11y/wakust-auto-sale/main/sale_state.json"
SALE_ARTICLES_JSON = Path(__file__).parent / "data" / "sale_articles.json"
ALL_DATA_JSON = Path(__file__).parent / "data" / "all_articles_data.json"


def fetch_sale_state():
    """wakust-auto-sale の sale_state.json を取得"""
    print(f"[INFO] sale_state.json を取得: {SALE_STATE_URL}")
    try:
        req = urllib.request.Request(SALE_STATE_URL, headers={"User-Agent": "ashitaka-magazine"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except urllib.error.HTTPError as e:
        print(f"[ERROR] HTTP {e.code}: {e.reason}")
        return None
    except Exception as e:
        print(f"[ERROR] 取得失敗: {e}")
        return None


def load_all_data():
    """all_articles_data.json からサムネイル等を補完するためのデータ"""
    if not ALL_DATA_JSON.exists():
        return {}
    with open(ALL_DATA_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {a.get("id", ""): a for a in data}


def main():
    print(f"=== セール記事連携 開始 ({datetime.now().isoformat()}) ===")

    sale_state = fetch_sale_state()
    if not sale_state:
        print("[ERROR] sale_state.json を取得できませんでした")
        return

    active_sales = sale_state.get("active_sales", [])
    print(f"[INFO] セール中の記事: {len(active_sales)}件")

    if not active_sales:
        # セールがない場合、空にする
        SALE_ARTICLES_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(SALE_ARTICLES_JSON, "w", encoding="utf-8") as f:
            json.dump([], f)
        print("[INFO] セール記事なし。sale_articles.json を空にしました")
        return

    # all_articles_data.json からサムネイル等を補完
    all_data = load_all_data()

    sale_articles = []
    for sale in active_sales:
        post_id = sale.get("post_id", "")
        title = sale.get("original_title", "")
        # セール文言を除去したタイトル
        title = title.replace("🔥今週のセール品🔥", "").strip()

        sale_price = sale.get("sale_price", 0)
        original_price = sale.get("original_price", 0)
        discount_label = sale.get("discount_label", "")
        area = sale.get("cat_name", "")

        # all_articles_data.json からサムネイルと日付を取得
        article_data = all_data.get(post_id, {})
        thumbnail = article_data.get("thumbnail", "")
        post_date = article_data.get("post_date", "")

        sale_article = {
            "slug": f"wakust-{post_id}",
            "title": title,
            "date": post_date,
            "area": area,
            "excerpt": f"{discount_label} {original_price}pt → {sale_price}pt",
            "thumbnail": thumbnail,
            "wakust_url": f"https://wakust.com/ryu-1992/{post_id}/",
            "sale_price": sale_price,
            "original_price": original_price,
            "discount_label": discount_label,
        }

        sale_articles.append(sale_article)
        print(f"[OK] {title[:40]}... ({discount_label} {original_price}→{sale_price}pt)")

    # 保存
    SALE_ARTICLES_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(SALE_ARTICLES_JSON, "w", encoding="utf-8") as f:
        json.dump(sale_articles, f, ensure_ascii=False, indent=2)

    print(f"[OK] sale_articles.json に {len(sale_articles)}件 保存しました")
    print(f"=== 完了 ({datetime.now().isoformat()}) ===")


if __name__ == "__main__":
    main()
