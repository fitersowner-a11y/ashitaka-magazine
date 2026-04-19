#!/usr/bin/env python3
"""
今週の無料記事 告知ツイートスクリプト (tweet_free_article.py)

select_free_article.py で選定された無料記事を X(Twitter) に告知する。
weekly-free.yml の中で select_free_article.py の直後に実行される。
"""

import json
import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

import tweepy

FREE_ARTICLE_JSON = Path(__file__).parent / "data" / "free_article.json"
SITE_URL = "https://menesthe-ashitaka.com"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_x_client():
    return tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
        wait_on_rate_limit=True,
    )


def build_tweet(article):
    title = article.get("title", "")
    slug = article.get("slug", "")
    area = article.get("area", "")
    url = f"{SITE_URL}/articles/{slug}/"

    # タイトルが長い場合は省略
    max_title = 60
    if len(title) > max_title:
        title = title[:max_title] + "…"

    tweet = (
        f"📖 今週の無料公開記事！\n\n"
        f"「{title}」\n\n"
        f"通常は有料の記事を、今週限定で全文無料公開中です。\n"
        f"月曜0時まで 読めます。\n\n"
        f"👉 {url}\n\n"
        f"#ワクスト #無料公開 #メンエス"
    )
    return tweet


def main():
    dry_run = "--dry-run" in sys.argv
    logger.info("=== 無料記事告知ツイート開始 ===")

    if not FREE_ARTICLE_JSON.exists():
        logger.error("free_article.json が見つかりません")
        return

    with open(FREE_ARTICLE_JSON, "r", encoding="utf-8") as f:
        article = json.load(f)

    if not article or not article.get("title"):
        logger.info("無料記事データが空です。スキップします。")
        return

    tweet_text = build_tweet(article)
    logger.info(f"ツイート内容:\n{tweet_text}")

    if dry_run:
        logger.info("[DRY RUN] 実際には投稿しません")
        return

    client = get_x_client()

    for attempt in range(3):
        try:
            response = client.create_tweet(text=tweet_text)
            tweet_id = str(response.data["id"])
            logger.info(f"ツイート投稿成功: {tweet_id}")
            return
        except tweepy.errors.TooManyRequests:
            wait = 60 * (2 ** attempt)
            logger.warning(f"レートリミット。{wait}秒後にリトライ ({attempt+1}/3)")
            time.sleep(wait)
        except tweepy.errors.TweepyException as e:
            logger.error(f"ツイート投稿失敗: {e}")
            return

    logger.error("リトライ上限に達しました")


if __name__ == "__main__":
    main()
