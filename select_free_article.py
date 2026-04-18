#!/usr/bin/env python3
"""
今週の無料記事選定スクリプト (select_free_article.py)

all_articles_data.json から古い記事（投稿90日以上）を1件選定し、
有料本文を含む全文を data/free_article.json に保存する。

毎週月曜に自動実行され、前週の無料記事を差し替える。

選定ルール:
1. 投稿から90日以上経過した記事が対象
2. 過去に無料公開済みの記事は除外（free_history.json で管理）
3. 対象からランダムに1件選出
"""

import json
import random
import os
from datetime import datetime, timedelta
from pathlib import Path

ALL_DATA_JSON = Path(__file__).parent / "data" / "all_articles_data.json"
FREE_ARTICLE_JSON = Path(__file__).parent / "data" / "free_article.json"
FREE_HISTORY_JSON = Path(__file__).parent / "data" / "free_history.json"

MIN_AGE_DAYS = 90  # 投稿からこの日数以上の記事が対象


def load_json(path):
    if not path.exists():
        return [] if path.name != "free_article.json" else {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    print(f"=== 今週の無料記事選定 開始 ({datetime.now().isoformat()}) ===")

    # 全記事データ読み込み
    all_articles = load_json(ALL_DATA_JSON)
    if not all_articles:
        print("[ERROR] all_articles_data.json が空です。先に fetch_all_data.py を実行してください。")
        return

    print(f"[INFO] 全記事数: {len(all_articles)}件")

    # 過去の無料公開履歴
    history = load_json(FREE_HISTORY_JSON)
    if not isinstance(history, list):
        history = []
    past_ids = {h["id"] for h in history}
    print(f"[INFO] 過去の無料公開数: {len(past_ids)}件")

    # 候補を絞り込み
    today = datetime.now()
    cutoff_date = today - timedelta(days=MIN_AGE_DAYS)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d")

    candidates = []
    for article in all_articles:
        article_id = article.get("id", "")
        post_date = article.get("post_date", "")

        # 投稿日がない記事はスキップ
        if not post_date:
            continue

        # 90日以上前の記事のみ
        if post_date > cutoff_str:
            continue

        # 過去に無料公開済みの記事はスキップ
        if article_id in past_ids:
            continue

        # 有料本文がない記事はスキップ
        if not article.get("paid_content"):
            continue

        candidates.append(article)

    print(f"[INFO] 無料公開候補: {len(candidates)}件（90日以上前 & 未公開 & 有料本文あり）")

    if not candidates:
        print("[WARN] 候補がありません。全記事が公開済みか条件に合いません。")
        # 候補がない場合、履歴をリセットして再選定
        if past_ids:
            print("[INFO] 履歴をリセットして再選定します。")
            history = []
            past_ids = set()
            for article in all_articles:
                if article.get("post_date", "") <= cutoff_str and article.get("paid_content"):
                    candidates.append(article)
            if not candidates:
                print("[ERROR] リセット後も候補がありません。終了します。")
                return

    # ランダムに1件選出
    selected = random.choice(candidates)
    print(f"[OK] 選定: {selected['title'][:50]}")
    print(f"     ID: {selected['id']}, 投稿日: {selected['post_date']}")
    print(f"     カテゴリー: {selected.get('category', '')}")
    print(f"     売上: {selected.get('sales_amount', 0)}pt")

    # 無料記事データを生成
    free_article = {
        "id": selected["id"],
        "slug": f"free-wakust-{selected['id']}",
        "title": selected["title"],
        "date": selected.get("post_date", ""),
        "area": selected.get("category", ""),
        "excerpt": selected.get("free_content", "")[:100],
        "free_content": selected.get("free_content", ""),
        "paid_content": selected.get("paid_content", ""),
        "thumbnail": selected.get("thumbnail", ""),
        "wakust_url": selected.get("wakust_url", ""),
        "selected_date": today.strftime("%Y-%m-%d"),
    }

    # 保存
    save_json(FREE_ARTICLE_JSON, free_article)
    print(f"[OK] free_article.json に保存しました")

    # 履歴に追加
    history.append({
        "id": selected["id"],
        "title": selected["title"],
        "selected_date": today.strftime("%Y-%m-%d"),
    })
    save_json(FREE_HISTORY_JSON, history)
    print(f"[OK] free_history.json に履歴追加（計 {len(history)}件）")

    print(f"=== 完了 ({datetime.now().isoformat()}) ===")


if __name__ == "__main__":
    main()
