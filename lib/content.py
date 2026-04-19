"""
lib/content.py
記事本文のクリーンアップと拡張を行う。
- ワクスト由来のナビゲーションゴミを除去
- 関連記事/エリア情報の追記で内部リンクとコンテンツ量を増強
"""

import re
import html
from lib.area import resolve_area_for_article, STATION_MASTER


# ============================================================
# ナビゲーションゴミのパターン
# ============================================================

# 完全一致で除去する定型文
_NOISE_EXACT = {
    "体験談(西)", "情報･創作", "情報・創作", "通常表示",
    "タイトル", "ユーザー", "タグ", "ホーム", "人気ランキング",
    "ログイン", "セット販売", "ロングセラー",
    "販売停止しています", "販売停止", "退店済み",
    "100円記事キャンペーン中！", "100円で記事が読める？初日キャンペーン実施中",
}

# 部分一致で除去する（タグ欄の特徴的な形式）
_NOISE_PATTERNS = [
    # "2025年02月21日 02:10 2026年04月07日 06:53" みたいな日付ペア
    re.compile(r'^\d{4}年\d{1,2}月\d{1,2}日\s+\d{1,2}:\d{2}(\s+\d{4}年\d{1,2}月\d{1,2}日\s+\d{1,2}:\d{2})?$'),
    # "メンエス厳選情報のアシタカ  5ムーン" みたいな筆者情報
    re.compile(r'^メンエス[^\s]*情報のアシタカ\s+\d+ムーン$'),
    # "メンエスのアシタカ(53)メンズエステ(75951)三軒茶屋(358)..." のようなタグ羅列
    re.compile(r'^([^\s（）()]+[（(]\d+[）)]\s*){2,}$'),
    # 数字のみの評価 "3.0" とか
    re.compile(r'^\d+\.\d+$'),
    # 空 or 極短
    re.compile(r'^.{0,3}$'),
]

# 記事タイトルの繰り返し（contentの末尾に「「記事タイトル」」として出がち）
def _is_title_echo(text, title):
    if not title:
        return False
    t = text.strip().strip('「」"\'')
    return t == title.strip() or (title.strip() in t and len(t) < len(title) + 10)


def _is_navigation_noise(text, title=""):
    """ナビゲーションゴミと判定されるか。"""
    t = text.strip()
    if not t:
        return True
    if t in _NOISE_EXACT:
        return True
    for pattern in _NOISE_PATTERNS:
        if pattern.match(t):
            return True
    # エリア名単独（「東京都」「神奈川県」「新宿」のような）
    if t in ("東京都", "神奈川県", "埼玉県", "千葉県", "多摩", "ノウハウ(リアル)", "ノウハウ(ネット)"):
        return True
    if t in STATION_MASTER:
        return True
    # タイトル繰り返し
    if _is_title_echo(t, title):
        return True
    return False


def clean_content(content_html, title=""):
    """
    記事のcontentフィールドからナビゲーションゴミを除去する。
    content_htmlは "<p>...</p>\n<p>...</p>" の形式を想定。
    """
    if not content_html:
        return ""

    # <p>...</p> を個別に抽出
    paragraphs = re.findall(r'<p>(.*?)</p>', content_html, re.DOTALL)

    cleaned = []
    for p in paragraphs:
        inner = p.strip()
        # HTMLタグを除去して比較用のテキストにする
        plain = re.sub(r'<[^>]+>', '', inner).strip()
        if _is_navigation_noise(plain, title):
            continue
        cleaned.append(f"<p>{inner}</p>")

    return "\n".join(cleaned)


def count_content_chars(content_html):
    """HTMLタグを除いた本文の文字数をカウント。"""
    if not content_html:
        return 0
    plain = re.sub(r'<[^>]+>', '', content_html)
    plain = re.sub(r'\s+', '', plain)
    return len(plain)


# ============================================================
# 関連記事ブロック生成（内部リンク強化）
# ============================================================

def generate_related_articles_block(article, all_articles, limit=6):
    """
    記事の下に表示する「関連記事」HTMLブロックを生成する。
    同エリア優先、日付が近い順。
    """
    current_slug = article.get("slug", "")
    current_info = resolve_area_for_article(article)
    current_area_slug = current_info["slug"] if current_info else None

    # 同エリアの他記事
    same_area = []
    other = []
    for other_article in all_articles:
        if other_article.get("slug") == current_slug:
            continue
        info = resolve_area_for_article(other_article)
        if info and info["slug"] == current_area_slug:
            same_area.append(other_article)
        else:
            other.append(other_article)

    # 日付降順
    same_area.sort(key=lambda a: a.get("date", ""), reverse=True)
    other.sort(key=lambda a: a.get("date", ""), reverse=True)

    # 同エリアから最大4件、足りなければ他エリアから補充
    selected = same_area[:4] + other[:max(0, limit - min(4, len(same_area)))]
    selected = selected[:limit]

    if not selected:
        return ""

    area_name = current_info["name"] if current_info else "同ジャンル"

    cards = []
    for a in selected:
        slug = a.get("slug", "")
        title = html.escape(a.get("title", ""))
        thumb = a.get("thumbnail", "")
        date = a.get("date", "")
        a_info = resolve_area_for_article(a)
        a_area = html.escape(a_info["name"]) if a_info else ""

        thumb_html = (
            f'<img src="{html.escape(thumb)}" alt="{title}" loading="lazy">'
            if thumb else '<span class="placeholder">📝</span>'
        )

        cards.append(f'''
        <a href="/articles/{slug}/" class="article-card">
          <div class="article-thumb">{thumb_html}</div>
          <div class="article-body">
            <div class="article-meta">{a_area} ・ {date}</div>
            <h3 class="article-title">{title}</h3>
          </div>
        </a>''')

    return "\n".join(cards)


# ============================================================
# エリアナビゲーションブロック（記事下部の他エリア誘導）
# ============================================================

def generate_area_nav_block(current_article, all_articles):
    """
    記事下部に表示する「他エリアから探す」ブロックを生成する。
    """
    from lib.area import group_articles_by_area

    current_info = resolve_area_for_article(current_article)
    current_slug = current_info["slug"] if current_info else None

    groups = group_articles_by_area(all_articles)

    # 親エリア別に整理
    by_parent = {}
    for slug, group in groups.items():
        info = group["info"]
        if not info or not info["is_station"]:
            continue  # 駅レベルのみ表示
        if slug == current_slug:
            continue
        parent = info["parent"]
        by_parent.setdefault(parent, []).append({
            "slug": slug,
            "name": info["name"],
            "count": len(group["articles"]),
        })

    # 件数順でソート
    parent_order = ["tokyo", "kanagawa", "tama", "saitama", "chiba"]
    parent_labels = {
        "tokyo": "東京都",
        "kanagawa": "神奈川県",
        "tama": "多摩地区",
        "saitama": "埼玉県",
        "chiba": "千葉県",
    }

    sections = []
    for parent in parent_order:
        if parent not in by_parent:
            continue
        areas = sorted(by_parent[parent], key=lambda x: x["count"], reverse=True)
        if not areas:
            continue
        links = " ・ ".join(
            f'<a href="/areas/{a["slug"]}/">{html.escape(a["name"])}（{a["count"]}）</a>'
            for a in areas
        )
        sections.append(f'<p><strong>{parent_labels[parent]}：</strong>{links}</p>')

    if not sections:
        return ""

    return f'''
    <section class="area-nav-block" style="margin-top: 40px; padding: 20px; background: #f7f9fc; border-radius: 8px; font-size: 14px; line-height: 1.8;">
      <h2 style="font-size: 16px; margin-top: 0;">📍 他のエリアのメンエス体験レポートを探す</h2>
      {''.join(sections)}
      <p style="margin-top: 12px;"><a href="/areas/">エリア一覧をすべて見る →</a></p>
    </section>'''


# ============================================================
# descriptionの自動生成
# ============================================================

def generate_meta_description(article, max_length=155):
    """
    記事のメタディスクリプションを自動生成する。
    優先順位: 清浄化された本文冒頭 > excerpt > タイトル
    """
    title = article.get("title", "")
    excerpt = article.get("excerpt", "")
    content = article.get("content", "")
    info = resolve_area_for_article(article)
    area_name = info["name"] if info else article.get("area", "")

    # クリーン後の本文からテキストを抽出
    cleaned = clean_content(content, title)
    plain = re.sub(r'<[^>]+>', '', cleaned)
    plain = re.sub(r'\s+', '', plain)

    # ソース選択
    source = None
    if plain and len(plain) >= 30:
        source = plain
    elif excerpt and not _is_navigation_noise(excerpt, title) and len(excerpt) >= 10:
        source = excerpt

    if source:
        base = source[:120]
    else:
        base = title[:80]

    # エリア情報を末尾に付加
    if area_name:
        suffix = f"｜{area_name}のメンズエステ体験レポート"
    else:
        suffix = "｜メンエス好きのアシタカマガジン"

    # 最大長に収める
    available = max_length - len(suffix) - 3  # "..."
    if len(base) > available:
        base = base[:available].rstrip("、。・") + "…"

    return base + suffix


def generate_meta_keywords(article):
    """
    記事のメタキーワードを生成する。
    """
    from lib.area import extract_genres, GENRE_PATTERNS

    info = resolve_area_for_article(article)
    keywords = []

    if info:
        keywords.extend(info["keywords"])

    # 系統タグ
    genres = extract_genres(article)
    for g in genres:
        if g in GENRE_PATTERNS:
            _patterns, label = GENRE_PATTERNS[g]
            keywords.append(label)

    # 共通キーワード
    keywords.extend(["メンエス", "メンズエステ", "体験談", "口コミ", "レビュー", "アシタカ"])

    # 重複除去・順序維持
    seen = set()
    result = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            result.append(k)

    return ",".join(result)
