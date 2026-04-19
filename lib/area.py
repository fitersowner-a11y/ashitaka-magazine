"""
lib/area.py
エリア・駅抽出とグルーピングロジック。
タイトル内の【〇〇/...】【〇〇｜...】【〇〇】パターンから駅名を抽出し、
SEO用のURLスラッグに変換する。
"""

import re
from collections import defaultdict


# ============================================================
# 駅・エリアマスタ
# ============================================================
# キー: 表記ゆれを吸収した「正規化後の駅名」
# 値: (slug, 表示名, 親エリア, 検索キーワード)
STATION_MASTER = {
    # --- 東京都・23区内 ---
    "秋葉原":     ("akihabara",      "秋葉原",      "tokyo",    ["秋葉原", "アキバ", "神田"]),
    "新宿":       ("shinjuku",       "新宿",        "tokyo",    ["新宿", "歌舞伎町", "新宿三丁目"]),
    "池袋":       ("ikebukuro",      "池袋",        "tokyo",    ["池袋", "新大久保"]),
    "麻布十番":   ("azabu-juban",    "麻布十番",    "tokyo",    ["麻布十番", "麻布", "六本木"]),
    "中目黒":     ("naka-meguro",    "中目黒",      "tokyo",    ["中目黒", "目黒"]),
    "三軒茶屋":   ("sangenjaya",     "三軒茶屋",    "tokyo",    ["三軒茶屋", "三茶"]),
    "赤坂":       ("akasaka",        "赤坂",        "tokyo",    ["赤坂", "溜池山王"]),
    "神田":       ("kanda",          "神田",        "tokyo",    ["神田"]),
    "新橋":       ("shinbashi",      "新橋",        "tokyo",    ["新橋", "銀座"]),
    "銀座":       ("ginza",          "銀座",        "tokyo",    ["銀座", "新橋"]),
    "上野":       ("ueno",           "上野",        "tokyo",    ["上野"]),
    "北千住":     ("kita-senju",     "北千住",      "tokyo",    ["北千住"]),
    "赤羽":       ("akabane",        "赤羽",        "tokyo",    ["赤羽"]),
    "五反田":     ("gotanda",        "五反田",      "tokyo",    ["五反田", "目黒", "大井町"]),
    "渋谷":       ("shibuya",        "渋谷",        "tokyo",    ["渋谷", "恵比寿"]),
    "神楽坂":     ("kagurazaka",     "神楽坂",      "tokyo",    ["神楽坂", "曙橋"]),
    "六本木":     ("roppongi",       "六本木",      "tokyo",    ["六本木"]),

    # --- 東京都・多摩地区 ---
    "立川":       ("tachikawa",      "立川",        "tama",     ["立川", "多摩"]),
    "八王子":     ("hachioji",       "八王子",      "tama",     ["八王子", "西八王子"]),

    # --- 神奈川県 ---
    "武蔵小杉":   ("musashi-kosugi", "武蔵小杉",    "kanagawa", ["武蔵小杉", "小杉"]),
    "横浜":       ("yokohama",       "横浜",        "kanagawa", ["横浜", "関内"]),
    "川崎":       ("kawasaki",       "川崎",        "kanagawa", ["川崎"]),
    "綱島":       ("tsunashima",     "綱島",        "kanagawa", ["綱島", "東横線"]),
    "新横浜":     ("shin-yokohama",  "新横浜",      "kanagawa", ["新横浜"]),
    "溝の口":     ("mizonokuchi",    "溝の口",      "kanagawa", ["溝の口", "溝口"]),
    "藤沢":       ("fujisawa",       "藤沢",        "kanagawa", ["藤沢", "湘南"]),

    # --- 埼玉県 ---
    "大宮":       ("omiya",          "大宮",        "saitama",  ["大宮", "さいたま"]),

    # --- 千葉県 ---
    "柏":         ("kashiwa",        "柏",          "chiba",    ["柏"]),
    "松戸":       ("matsudo",        "松戸",        "chiba",    ["松戸", "新松戸"]),
    "船橋":       ("funabashi",      "船橋",        "chiba",    ["船橋", "西船橋"]),
    "千葉":       ("chiba-city",     "千葉駅",      "chiba",    ["千葉駅", "千葉"]),
}


# タイトル内の表記ゆれを吸収するマップ
# （タイトル表記 → STATION_MASTERのキー）
STATION_ALIASES = {
    # タイポや異表記
    "麻生十番": "麻布十番",
    "大森":     "中目黒",   # 記事1件のみのため近いエリアに吸収
    "関内":     "横浜",
    "新松戸":   "松戸",
    "西船橋":   "船橋",
    "千葉駅":   "千葉",
    "西八王子": "八王子",
    "曙橋":     "神楽坂",
    "新大久保": "新宿",
    "日本橋":   "神田",     # 東京の日本橋（大阪の日本橋ではない）を神田エリアに
    "中野":     "新宿",
    "溝口":     "溝の口",
    "恵比寿":   "渋谷",
    "目黒":     "五反田",
    "大井町":   "五反田",
    "湘南":     "藤沢",
    "歌舞伎町": "新宿",
    "新宿三丁目": "新宿",
    "三茶":     "三軒茶屋",
    "アキバ":   "秋葉原",
    "小杉":     "武蔵小杉",
    "麻布":     "麻布十番",
}


# タイトルでは駅名が出ないが、areaフィールドで分類したい場合のフォールバック
AREA_FALLBACK = {
    "東京都":       ("tokyo-other",     "東京都（その他）", "tokyo",    ["東京"]),
    "神奈川県":     ("kanagawa-other",  "神奈川県（その他）", "kanagawa", ["神奈川"]),
    "埼玉県":       ("saitama-other",   "埼玉県（その他）", "saitama",  ["埼玉"]),
    "千葉県":       ("chiba-other",     "千葉県（その他）", "chiba",    ["千葉"]),
    "多摩":         ("tama-other",      "多摩地区",         "tama",     ["多摩"]),
    "ノウハウ(リアル)": ("nouhau-real",  "メンエスノウハウ（リアル）", "nouhau", ["ノウハウ"]),
    "ノウハウ(ネット)": ("nouhau-net",   "メンエスノウハウ（ネット）", "nouhau", ["ノウハウ"]),
}


# 親エリアの定義
PARENT_AREA_MASTER = {
    "tokyo":    ("東京都",       "Tokyo"),
    "tama":     ("多摩地区",     "Tama"),
    "kanagawa": ("神奈川県",     "Kanagawa"),
    "saitama":  ("埼玉県",       "Saitama"),
    "chiba":    ("千葉県",       "Chiba"),
    "nouhau":   ("ノウハウ",     "Know-how"),
}


# ============================================================
# 駅名抽出ロジック
# ============================================================

# タイトル内の駅名候補を抽出する正規表現（優先順）
_STATION_EXTRACT_PATTERNS = [
    # 【秋葉原/爆乳】【新宿｜Gカップ】【立川/激震】
    re.compile(r'【([^/｜\|\]】]+?)[\s]*[/／｜\|][^】]*】'),
    # 【立川】【秋葉原】（単独）
    re.compile(r'【([^】/／｜\|]+?)】'),
    # -中目黒- や ‐池袋‐ のようなハイフン区切り
    re.compile(r'[-‐‑]([^\s\-‐‑]{2,8})[-‐‑]'),
    # 「新宿」「池袋」などエリア名の単純出現（末尾マッチ）
    re.compile(r'[^\w]([^\s\W]{2,6})$'),
]


def _normalize_station_name(raw):
    """駅名候補を正規化する。エイリアスを解決し、マスタにない場合はNone。"""
    if not raw:
        return None
    raw = raw.strip()

    # ノイズ除去
    for noise in ["退店済み", "閉店", "販売停止", "★", "🔥", "㊙", "※",
                  "衝撃の", "速報", "限定", "最新版", "新人発掘"]:
        raw = raw.replace(noise, "")
    raw = raw.strip()

    if not raw or len(raw) < 2:
        return None

    # エイリアス解決
    if raw in STATION_ALIASES:
        raw = STATION_ALIASES[raw]

    # マスタに存在するか
    if raw in STATION_MASTER:
        return raw

    # 部分一致（「秋葉原Gカップ」→「秋葉原」）
    for master_key in STATION_MASTER.keys():
        if master_key in raw and len(master_key) >= 2:
            return master_key
    for alias_key, master_key in STATION_ALIASES.items():
        if alias_key in raw and len(alias_key) >= 2:
            return master_key

    return None


def extract_station(article):
    """
    記事から駅名（STATION_MASTERのキー）を抽出する。
    見つからなければ None を返す。
    """
    title = article.get("title", "")

    # タイトルから正規表現で抽出
    for pattern in _STATION_EXTRACT_PATTERNS:
        for match in pattern.finditer(title):
            candidate = match.group(1)
            normalized = _normalize_station_name(candidate)
            if normalized:
                return normalized

    # タイトル全体に対して駅名マスタを部分一致で探す（最終フォールバック）
    for master_key in STATION_MASTER.keys():
        if master_key in title:
            return master_key
    for alias_key, master_key in STATION_ALIASES.items():
        if alias_key in title:
            return master_key

    return None


def resolve_area_for_article(article):
    """
    記事のエリア情報を解決する。
    駅が抽出できればそれを、できなければ area フィールドからフォールバック分類。

    戻り値: dict {
        "slug": str,
        "name": str,
        "parent": str,
        "keywords": list,
        "is_station": bool  # 駅レベルのページか、都道府県レベルか
    }
    または None（分類不能）
    """
    # 1. まずタイトルから駅名を抽出
    station = extract_station(article)
    if station and station in STATION_MASTER:
        slug, name, parent, keywords = STATION_MASTER[station]
        return {
            "slug": slug,
            "name": name,
            "parent": parent,
            "keywords": keywords,
            "is_station": True,
        }

    # 2. フォールバック: areaフィールドで分類
    area = article.get("area", "")
    if area in AREA_FALLBACK:
        slug, name, parent, keywords = AREA_FALLBACK[area]
        return {
            "slug": slug,
            "name": name,
            "parent": parent,
            "keywords": keywords,
            "is_station": False,
        }

    # 3. areaフィールド自体がSTATION_MASTERにある（例: area="新宿"）
    if area in STATION_MASTER:
        slug, name, parent, keywords = STATION_MASTER[area]
        return {
            "slug": slug,
            "name": name,
            "parent": parent,
            "keywords": keywords,
            "is_station": True,
        }

    return None


# ============================================================
# グルーピング
# ============================================================

def group_articles_by_area(articles):
    """
    記事を駅/エリアごとにグルーピングする。
    戻り値: {
        "akihabara": {
            "info": {"slug": "akihabara", "name": "秋葉原", ...},
            "articles": [article, article, ...]
        },
        ...
    }
    """
    groups = defaultdict(lambda: {"info": None, "articles": []})

    for article in articles:
        info = resolve_area_for_article(article)
        if not info:
            continue
        slug = info["slug"]
        if groups[slug]["info"] is None:
            groups[slug]["info"] = info
        groups[slug]["articles"].append(article)

    # 日付降順でソート
    for slug, group in groups.items():
        group["articles"].sort(key=lambda a: a.get("date", ""), reverse=True)

    return dict(groups)


def group_by_parent_area(area_groups):
    """
    エリアグループをさらに親エリア（都道府県）単位でまとめる。
    戻り値: {
        "tokyo": [{"slug": "akihabara", "name": "秋葉原", "count": 24}, ...],
        ...
    }
    """
    parents = defaultdict(list)
    for slug, group in area_groups.items():
        info = group["info"]
        if not info:
            continue
        parents[info["parent"]].append({
            "slug": info["slug"],
            "name": info["name"],
            "is_station": info["is_station"],
            "count": len(group["articles"]),
        })

    # 件数降順でソート
    for parent_key, areas in parents.items():
        areas.sort(key=lambda a: a["count"], reverse=True)

    return dict(parents)


# ============================================================
# 系統タグ分類（爆乳/スレンダー/人妻/ロリなど）
# ============================================================

# タイトルから系統タグを推定する
GENRE_PATTERNS = {
    "bakunyu":   (["爆乳", "巨乳", "Gカップ", "Hカップ", "Iカップ", "Fカップ", "Eカップ", "超乳", "神乳", "美乳"], "爆乳・巨乳"),
    "slender":   (["スレンダー", "モデル", "細身", "美脚", "長身"], "スレンダー"),
    "hitozuma":  (["人妻", "熟女", "美魔女", "お姉さん", "30代", "40代", "マダム"], "人妻・熟女"),
    "loli":      (["ロリ", "JD", "10代", "19歳", "20歳", "21歳", "22歳", "現役", "ギャル", "学生"], "ロリ・若い"),
    "moto":      (["元", "引退", "伝説", "元ラウンジ", "元ナース", "元アイドル"], "元・経験者"),
    "gaihin":    (["ハーフ", "南米", "褐色", "外国", "金髪"], "ハーフ・外国系"),
}


def extract_genres(article):
    """記事から系統タグのsetを抽出。"""
    title = article.get("title", "")
    found = set()
    for genre_key, (patterns, _label) in GENRE_PATTERNS.items():
        for p in patterns:
            if p in title:
                found.add(genre_key)
                break
    return found


# ============================================================
# v3互換ヘルパー
# ============================================================

def area_to_filter_key_v3_compat(area):
    """
    v3のarea_to_filter_key相当。記事一覧ページのカテゴリーフィルター用。
    """
    mapping = {
        "東京都": "tokyo", "新宿": "tokyo", "池袋": "tokyo", "多摩": "tokyo",
        "神奈川県": "kanagawa",
        "埼玉県": "saitama",
        "千葉県": "chiba",
        "大阪府": "osaka", "日本橋": "osaka",
        "愛知県": "aichi", "栄": "aichi",
        "兵庫県": "hyogo",
        "福岡県": "fukuoka",
    }
    return mapping.get(area, "other")
