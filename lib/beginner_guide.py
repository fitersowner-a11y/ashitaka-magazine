"""
lib/beginner_guide.py
初心者ガイド（4コマ漫画シリーズ）ページを生成する。
- /beginner-guide/             一覧ページ
- /beginner-guide/characters/  キャラクター紹介
- /beginner-guide/{slug}/      各話ページ
"""

import os
import re
import html
import json
from datetime import datetime

from lib.seo import (
    generate_head_meta, generate_breadcrumb_jsonld,
    generate_breadcrumb_html, SITE_URL, SITE_NAME, AUTHOR_NAME,
)


BASE_PATH = "/beginner-guide"

_CATEGORY_META = {
    "basics": ("基本・予約", "basics"),
    "price":  ("料金",       "price"),
    "area":   ("エリア",     "area"),
}

_DIALOGUE_SPEAKERS = {
    "ki":    ("起", "kohai"),
    "sho":   ("承", "shisho"),
    "ten":   ("転", "kohai"),
    "ketsu": ("結", "shisho"),
}


# ============================================================
# データ読み込み
# ============================================================

def load_data(data_path):
    """data/beginner_guide.jsonを読み込む"""
    with open(str(data_path), "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# Markdown → HTML 変換
# ============================================================

def render_markdown(md_text):
    """Markdown→HTML変換（commentary_md用）"""
    if not md_text:
        return ""

    # コードブロックをプレースホルダに退避
    stash = []

    def _stash(m):
        idx = len(stash)
        stash.append(f'<pre><code>{html.escape(m.group(1).strip())}</code></pre>')
        return f"BGCODEBLOCK{idx}END"

    text = re.sub(r"```[^\n]*\n(.*?)```", _stash, md_text, flags=re.DOTALL)

    def _inline(t):
        t = html.escape(t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
        return t

    result = []
    in_ul = False
    in_table = False
    pending_header = None

    def _close_ul():
        nonlocal in_ul
        if in_ul:
            result.append("</ul>")
            in_ul = False

    def _close_table():
        nonlocal in_table
        if in_table:
            result.append("</tbody></table>")
            in_table = False

    for line in text.split("\n"):
        s = line.strip()

        # コードブロック復元
        m = re.match(r"^BGCODEBLOCK(\d+)END$", s)
        if m:
            _close_ul()
            _close_table()
            result.append(stash[int(m.group(1))])
            continue

        if s.startswith("## "):
            _close_ul(); _close_table()
            result.append(f"<h2>{_inline(s[3:])}</h2>")
        elif s.startswith("### "):
            _close_ul(); _close_table()
            result.append(f"<h3>{_inline(s[4:])}</h3>")
        elif s.startswith("- "):
            _close_table()
            if not in_ul:
                result.append("<ul>"); in_ul = True
            result.append(f"<li>{_inline(s[2:])}</li>")
        elif re.match(r"^\|[\|\-\:\s]+\|$", s):
            # テーブルセパレータ行
            if pending_header is not None:
                _close_ul()
                cols = [c.strip() for c in pending_header.strip("|").split("|")]
                result.append('<table class="bg-table"><thead><tr>')
                for c in cols:
                    result.append(f"<th>{_inline(c)}</th>")
                result.append("</tr></thead><tbody>")
                in_table = True
                pending_header = None
        elif s.startswith("|") and s.endswith("|"):
            _close_ul()
            if in_table:
                cols = [c.strip() for c in s.strip("|").split("|")]
                result.append("<tr>")
                for c in cols:
                    result.append(f"<td>{_inline(c)}</td>")
                result.append("</tr>")
            else:
                pending_header = s
        elif not s:
            _close_ul(); _close_table()
            pending_header = None
        elif s.startswith("1. ") or re.match(r"^\d+\. ", s):
            # 番号付きリストを段落として処理（簡易）
            _close_table()
            if not in_ul:
                result.append("<ul>"); in_ul = True
            item = re.sub(r"^\d+\. ", "", s)
            result.append(f"<li>{_inline(item)}</li>")
        else:
            _close_ul(); _close_table()
            result.append(f"<p>{_inline(s)}</p>")

    _close_ul()
    _close_table()

    return "\n".join(r for r in result if r)


# ============================================================
# データ引き当てヘルパー
# ============================================================

def get_related_episodes(slugs, all_episodes):
    """関連話slugから該当エピソードを引く"""
    slug_map = {ep["slug"]: ep for ep in all_episodes}
    return [slug_map[s] for s in slugs if s in slug_map]


def get_related_articles(slugs, all_articles):
    """関連記事slugから既存記事データを引く。見つからないslugはスキップ（警告print）"""
    slug_map = {a.get("slug", ""): a for a in all_articles}
    result = []
    for s in slugs:
        if s in slug_map:
            result.append(slug_map[s])
        else:
            print(f"  [警告] beginner_guide: related_article_slug '{s}' が見つかりません")
    return result


def get_related_areas(slugs, area_data):
    """関連エリアslugから既存エリアデータを引く。見つからないslugはスキップ"""
    result = []
    for s in slugs:
        if s in area_data:
            info = area_data[s].get("info") or {}
            result.append({"slug": s, "name": info.get("name", s)})
        else:
            print(f"  [警告] beginner_guide: related_area_slug '{s}' が見つかりません")
    return result


def get_prev_next(current, all_episodes):
    """episode_numberで前後のエピソードを取得"""
    sorted_eps = sorted(all_episodes, key=lambda e: e["episode_number"])
    num = current["episode_number"]
    prev_ep = next((e for e in sorted_eps if e["episode_number"] == num - 1), None)
    next_ep = next((e for e in sorted_eps if e["episode_number"] == num + 1), None)
    return prev_ep, next_ep


# ============================================================
# HTML部品生成
# ============================================================

def _category_label_html(cat_id):
    label, cls = _CATEGORY_META.get(cat_id, (cat_id, "other"))
    return f'<span class="bg-cat-label bg-cat-{cls}">{html.escape(label)}</span>'


def _tags_html(tags):
    return " ".join(f'<span class="bg-tag">{html.escape(t)}</span>' for t in tags)


def _manga_images_html(episode):
    slug = episode["slug"]
    ep_num = episode["episode_number"]
    title = episode["title"]
    parts = []
    for page in episode.get("pages", []):
        src = f"/beginner-guide/images/{slug}/{page}"
        alt = html.escape(f"第{ep_num}話 {title} - 4コマ漫画")
        parts.append(f'<img src="{src}" alt="{alt}" class="bg-manga-page" loading="lazy">')
    return "\n".join(parts)


def _dialogue_html(dialogue):
    parts = ['<div class="bg-dialogue">',
             '<p class="bg-dialogue-title">◎ 対話要約（起承転結）</p>']
    for key in ["ki", "sho", "ten", "ketsu"]:
        text = dialogue.get(key, "")
        if not text:
            continue
        label, speaker_class = _DIALOGUE_SPEAKERS[key]
        parts.append(
            f'<div class="bg-dialogue-line bg-{speaker_class}">'
            f'<span class="bg-dialogue-label">{label}</span>'
            f'<p>{html.escape(text)}</p>'
            f'</div>'
        )
    parts.append("</div>")
    return "\n".join(parts)


def _related_areas_html(areas):
    if not areas:
        return ""
    cards = "".join(
        f'<a href="/areas/{a["slug"]}/" class="bg-related-card">'
        f'<span class="bg-related-icon">📍</span>'
        f'<span>{html.escape(a["name"])}エリアページを見る</span>'
        f'</a>'
        for a in areas
    )
    return (
        '<div class="bg-related-block">'
        '<h2 class="section-title" style="font-size:16px;">このエリアの詳細を見る</h2>'
        f'<div class="bg-related-grid">{cards}</div>'
        '</div>'
    )


def _related_episodes_html(episodes):
    if not episodes:
        return ""
    cards = "".join(
        f'<a href="/beginner-guide/{ep["slug"]}/" class="bg-related-card">'
        f'<span class="bg-ep-badge">第{ep["episode_number"]}話</span>'
        f'<div><strong>{html.escape(ep["title"])}</strong>'
        f'<p class="bg-related-desc">{html.escape(ep.get("description", "")[:80])}</p></div>'
        f'</a>'
        for ep in episodes
    )
    return (
        '<div class="bg-related-block">'
        '<h2 class="section-title" style="font-size:16px;">関連する話を読む</h2>'
        f'<div class="bg-related-grid">{cards}</div>'
        '</div>'
    )


def _related_articles_html(articles):
    if not articles:
        return ""
    cards = []
    for a in articles:
        slug = a.get("slug", "")
        title = html.escape(a.get("title", ""))
        thumb = a.get("thumbnail", "")
        thumb_html = (
            f'<img src="{html.escape(thumb)}" alt="{title}" loading="lazy">'
            if thumb else ""
        )
        cards.append(
            f'<a href="/articles/{slug}/" class="article-card">'
            f'<div class="article-thumb">{thumb_html}</div>'
            f'<div class="article-body"><h3 class="article-title">{title}</h3></div>'
            f'</a>'
        )
    return (
        '<div class="bg-related-block">'
        '<h2 class="section-title" style="font-size:16px;">関連記事</h2>'
        f'<div class="articles-grid">{"".join(cards)}</div>'
        '</div>'
    )


def _wakust_cta_html(cta):
    if not cta.get("enabled"):
        return ""
    url = html.escape(cta.get("url", ""))
    label = html.escape(cta.get("label", "ワクストで詳しく読む"))
    return (
        f'<div class="wakust-cta">'
        f'<a href="{url}" class="btn" target="_blank" rel="noopener sponsored nofollow">'
        f'{label} →</a>'
        f'</div>'
    )


def _prev_next_html(prev_ep, next_ep):
    parts = ['<nav class="bg-prev-next" aria-label="前後のエピソード">']
    if prev_ep:
        parts.append(
            f'<a href="/beginner-guide/{prev_ep["slug"]}/" class="bg-nav-prev">'
            f'← 第{prev_ep["episode_number"]}話: {html.escape(prev_ep["title"])}</a>'
        )
    else:
        parts.append('<span class="bg-nav-placeholder"></span>')
    if next_ep:
        parts.append(
            f'<a href="/beginner-guide/{next_ep["slug"]}/" class="bg-nav-next">'
            f'第{next_ep["episode_number"]}話: {html.escape(next_ep["title"])} →</a>'
        )
    else:
        parts.append('<span class="bg-nav-placeholder"></span>')
    parts.append("</nav>")
    return "\n".join(parts)


# ============================================================
# 各話ページ生成
# ============================================================

def build_episode_page(episode, series_meta, characters, all_episodes,
                       all_articles, area_data, templates, output_dir, ga4_tag=""):
    """各話のHTMLを生成"""
    slug = episode["slug"]
    ep_num = episode["episode_number"]
    title = episode["title"]
    subtitle = episode.get("subtitle", "")
    description = episode.get("description", "")
    url = f"{BASE_PATH}/{slug}/"
    published_at = episode.get("published_at", "")
    cat_id = episode.get("category", "")
    cover_image_url = f"{SITE_URL}{BASE_PATH}/images/{slug}/{episode.get('cover_image', 'cover.png')}"

    head_meta = generate_head_meta(
        title=f"第{ep_num}話: {title}【初心者ガイド】",
        description=description[:155],
        url=url,
        page_type="article",
        image=cover_image_url,
        keywords=",".join(episode.get("tags", [])) + ",初心者ガイド,メンエス,メンズエステ",
        article_date=published_at,
        article_section="初心者ガイド",
    )

    breadcrumb_items = [
        {"name": "ホーム", "url": "/"},
        {"name": "初心者ガイド", "url": f"{BASE_PATH}/"},
        {"name": f"第{ep_num}話 {title}"},
    ]
    article_data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": f"第{ep_num}話: {title}",
        "description": description[:155],
        "url": f"{SITE_URL}{url}",
        "datePublished": published_at,
        "dateModified": published_at,
        "inLanguage": "ja",
        "author": {"@type": "Person", "name": AUTHOR_NAME, "url": f"{SITE_URL}/about/"},
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": f"{SITE_URL}/"},
        "image": {"@type": "ImageObject", "url": cover_image_url},
        "mainEntityOfPage": {"@type": "WebPage", "@id": f"{SITE_URL}{url}"},
    }
    import json as _json
    article_jsonld = f'<script type="application/ld+json">{_json.dumps(article_data, ensure_ascii=False, separators=(",", ":"))}</script>'
    jsonld = f"{article_jsonld}\n  {generate_breadcrumb_jsonld(breadcrumb_items)}"

    related_areas = get_related_areas(episode.get("related_area_slugs", []), area_data)
    related_eps = get_related_episodes(episode.get("related_episode_slugs", []), all_episodes)
    related_arts = get_related_articles(episode.get("related_article_slugs", []), all_articles)
    prev_ep, next_ep = get_prev_next(episode, all_episodes)

    html_out = templates["episode"]
    replacements = {
        "{{HEAD_META}}":          head_meta,
        "{{JSON_LD}}":            jsonld,
        "{{GA4_TAG}}":            ga4_tag,
        "{{BREADCRUMB_HTML}}":    generate_breadcrumb_html(breadcrumb_items),
        "{{EP_NUMBER}}":          str(ep_num),
        "{{TITLE}}":              html.escape(title),
        "{{SUBTITLE}}":           html.escape(subtitle),
        "{{DATE}}":               published_at,
        "{{CATEGORY_LABEL}}":     _category_label_html(cat_id),
        "{{TAGS_HTML}}":          _tags_html(episode.get("tags", [])),
        "{{MANGA_IMAGES}}":       _manga_images_html(episode),
        "{{DIALOGUE_HTML}}":      _dialogue_html(episode.get("dialogue_summary", {})),
        "{{COMMENTARY}}":         render_markdown(episode.get("commentary_md", "")),
        "{{RELATED_AREAS}}":      _related_areas_html(related_areas),
        "{{RELATED_EPISODES}}":   _related_episodes_html(related_eps),
        "{{RELATED_ARTICLES}}":   _related_articles_html(related_arts),
        "{{WAKUST_CTA}}":         _wakust_cta_html(episode.get("wakust_cta", {})),
        "{{PREV_NEXT}}":          _prev_next_html(prev_ep, next_ep),
    }
    for k, v in replacements.items():
        html_out = html_out.replace(k, v)

    ep_dir = os.path.join(str(output_dir), slug)
    os.makedirs(ep_dir, exist_ok=True)
    with open(os.path.join(ep_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_out)


# ============================================================
# 一覧ページ生成
# ============================================================

def _episode_card_html(episode):
    slug = episode["slug"]
    ep_num = episode["episode_number"]
    title = html.escape(episode["title"])
    subtitle = html.escape(episode.get("subtitle", ""))
    desc = html.escape(episode.get("description", "")[:100])
    cat_id = episode.get("category", "")
    cover = f"/beginner-guide/images/{slug}/{episode.get('cover_image', 'cover.png')}"

    return f'''
    <a href="/beginner-guide/{slug}/" class="bg-episode-card" data-category="{cat_id}">
      <div class="bg-episode-thumb">
        <img src="{cover}" alt="第{ep_num}話 {title}" loading="lazy">
        <span class="bg-ep-badge">第{ep_num}話</span>
      </div>
      <div class="bg-episode-body">
        {_category_label_html(cat_id)}
        <h3 class="bg-episode-title">{title}</h3>
        <p class="bg-episode-subtitle">{subtitle}</p>
        <p class="bg-episode-desc">{desc}…</p>
        <div class="bg-episode-tags">{_tags_html(episode.get("tags", []))}</div>
        <span class="article-read-more">読む →</span>
      </div>
    </a>'''


def build_index_page(series_meta, characters, episodes, categories,
                     templates, output_dir, ga4_tag=""):
    """一覧ページのHTMLを生成"""
    url = f"{BASE_PATH}/"
    cover_url = f"{SITE_URL}{BASE_PATH}/images/characters/{series_meta.get('cover_image', 'series-cover.png')}"

    head_meta = generate_head_meta(
        title=series_meta["title"],
        description=series_meta["description"][:155],
        url=url,
        page_type="website",
        image=cover_url,
        keywords="初心者ガイド,メンエス,メンズエステ,4コマ漫画,師匠,後輩くん",
    )

    breadcrumb_items = [
        {"name": "ホーム", "url": "/"},
        {"name": "初心者ガイド"},
    ]
    import json as _json
    collection_data = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": series_meta["title"],
        "description": series_meta["description"],
        "url": f"{SITE_URL}{url}",
        "inLanguage": "ja",
        "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": f"{SITE_URL}/"},
    }
    collection_jsonld = f'<script type="application/ld+json">{_json.dumps(collection_data, ensure_ascii=False, separators=(",", ":"))}</script>'
    jsonld = f"{collection_jsonld}\n  {generate_breadcrumb_jsonld(breadcrumb_items)}"

    sorted_eps = sorted(episodes, key=lambda e: (
        next((c["order"] for c in categories if c["id"] == e.get("category")), 99),
        e["episode_number"]
    ))
    episode_cards = "\n".join(_episode_card_html(ep) for ep in sorted_eps)

    cat_tabs = '<button class="filter-btn active" data-filter="all">すべて</button>\n'
    for cat in sorted(categories, key=lambda c: c["order"]):
        cat_tabs += f'        <button class="filter-btn" data-filter="{cat["id"]}">{html.escape(cat["label"])}</button>\n'

    html_out = templates["index"]
    replacements = {
        "{{HEAD_META}}":          head_meta,
        "{{JSON_LD}}":            jsonld,
        "{{GA4_TAG}}":            ga4_tag,
        "{{BREADCRUMB_HTML}}":    generate_breadcrumb_html(breadcrumb_items),
        "{{SERIES_TITLE}}":       html.escape(series_meta["title"]),
        "{{CATCHCOPY}}":          html.escape(series_meta.get("catchcopy", "")),
        "{{SERIES_DESCRIPTION}}": html.escape(series_meta["description"]),
        "{{CATEGORY_TABS}}":      cat_tabs,
        "{{EPISODE_CARDS}}":      episode_cards,
    }
    for k, v in replacements.items():
        html_out = html_out.replace(k, v)

    os.makedirs(str(output_dir), exist_ok=True)
    with open(os.path.join(str(output_dir), "index.html"), "w", encoding="utf-8") as f:
        f.write(html_out)


# ============================================================
# キャラクター紹介ページ生成
# ============================================================

def _character_profile_html(char):
    image_src = f"/beginner-guide/images/characters/{char.get('image', '')}"
    name = html.escape(char["name"])
    reading = html.escape(char.get("name_reading", ""))
    char_id = char.get("id", "")

    return f'''
    <div class="bg-character-card bg-char-{char_id}">
      <div class="bg-character-image">
        <img src="{image_src}" alt="{name}のキャラクター画像" loading="lazy">
      </div>
      <div class="bg-character-profile">
        <h2 class="bg-character-name">{name} <span class="bg-char-reading">（{reading}）</span></h2>
        <dl class="bg-character-dl">
          <dt>年齢</dt><dd>{html.escape(char.get("age", ""))}</dd>
          <dt>職業</dt><dd>{html.escape(char.get("occupation", ""))}</dd>
          <dt>特徴</dt><dd>{html.escape(char.get("traits", ""))}</dd>
          <dt>役割</dt><dd>{html.escape(char.get("role", ""))}</dd>
        </dl>
      </div>
    </div>'''


def build_characters_page(series_meta, characters, episodes,
                          templates, output_dir, ga4_tag=""):
    """キャラクター紹介ページのHTMLを生成"""
    url = f"{BASE_PATH}/characters/"

    head_meta = generate_head_meta(
        title=f"登場キャラクター紹介 | {series_meta['short_title']}",
        description=f"師匠と後輩くんのキャラクター紹介。{series_meta['description'][:100]}",
        url=url,
        page_type="website",
    )

    breadcrumb_items = [
        {"name": "ホーム", "url": "/"},
        {"name": "初心者ガイド", "url": f"{BASE_PATH}/"},
        {"name": "キャラクター紹介"},
    ]
    import json as _json
    webpage_data = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": f"登場キャラクター紹介 | {series_meta['title']}",
        "url": f"{SITE_URL}{url}",
        "inLanguage": "ja",
        "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": f"{SITE_URL}/"},
    }
    webpage_jsonld = f'<script type="application/ld+json">{_json.dumps(webpage_data, ensure_ascii=False, separators=(",", ":"))}</script>'
    jsonld = f"{webpage_jsonld}\n  {generate_breadcrumb_jsonld(breadcrumb_items)}"

    characters_html = "\n".join(_character_profile_html(c) for c in characters)

    latest = max(episodes, key=lambda e: e["episode_number"]) if episodes else None
    latest_link = ""
    if latest:
        latest_link = (
            f'<a href="/beginner-guide/{latest["slug"]}/" class="btn">'
            f'最新: 第{latest["episode_number"]}話「{html.escape(latest["title"])}」を読む →</a>'
        )

    html_out = templates["characters"]
    replacements = {
        "{{HEAD_META}}":           head_meta,
        "{{JSON_LD}}":             jsonld,
        "{{GA4_TAG}}":             ga4_tag,
        "{{BREADCRUMB_HTML}}":     generate_breadcrumb_html(breadcrumb_items),
        "{{CHARACTERS_HTML}}":     characters_html,
        "{{LATEST_EPISODE_LINK}}": latest_link,
    }
    for k, v in replacements.items():
        html_out = html_out.replace(k, v)

    chars_dir = os.path.join(str(output_dir), "characters")
    os.makedirs(chars_dir, exist_ok=True)
    with open(os.path.join(chars_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_out)


# ============================================================
# サイトマップ用URL
# ============================================================

def get_sitemap_urls(episodes, base_url):
    """サイトマップ用URL一覧を返す（一覧・キャラ紹介・全話）"""
    today = datetime.now().strftime("%Y-%m-%d")
    urls = [
        {
            "loc": f"{base_url}/beginner-guide/",
            "lastmod": today,
            "changefreq": "weekly",
            "priority": "0.8",
            "images": [],
        },
        {
            "loc": f"{base_url}/beginner-guide/characters/",
            "lastmod": today,
            "changefreq": "monthly",
            "priority": "0.6",
            "images": [],
        },
    ]
    for ep in episodes:
        slug = ep["slug"]
        cover = ep.get("cover_image", "cover.png")
        images = [{"loc": f"{base_url}/beginner-guide/images/{slug}/{cover}",
                   "title": f"第{ep['episode_number']}話 {ep['title']}"}]
        for page in ep.get("pages", []):
            if page != cover:
                images.append({"loc": f"{base_url}/beginner-guide/images/{slug}/{page}",
                                "title": f"第{ep['episode_number']}話 {ep['title']}"})
        urls.append({
            "loc": f"{base_url}/beginner-guide/{slug}/",
            "lastmod": ep.get("published_at", today),
            "changefreq": "monthly",
            "priority": "0.7",
            "images": images,
        })
    return urls


# ============================================================
# エントリポイント
# ============================================================

def build_all(data_path, all_articles, area_data, templates, output_dir, ga4_tag=""):
    """
    エントリポイント。loadしてindex・characters・各話を全部ビルド。
    返り値: {"series_meta": ..., "episodes": ..., "characters": ...}
    """
    data = load_data(data_path)
    series_meta = data["series_meta"]
    characters = data["characters"]
    episodes = data["episodes"]
    categories = data["categories"]

    output_dir_str = str(output_dir)

    # 画像ディレクトリ作成（実画像はユーザーが後日配置）
    os.makedirs(os.path.join(output_dir_str, "images", "characters"), exist_ok=True)
    for ep in episodes:
        os.makedirs(os.path.join(output_dir_str, "images", ep["slug"]), exist_ok=True)

    build_index_page(series_meta, characters, episodes, categories,
                     templates, output_dir_str, ga4_tag)

    build_characters_page(series_meta, characters, episodes,
                          templates, output_dir_str, ga4_tag)

    for ep in episodes:
        build_episode_page(ep, series_meta, characters, episodes,
                           all_articles, area_data, templates, output_dir_str, ga4_tag)

    print(f"  初心者ガイド: {len(episodes)}話 + 一覧 + キャラクター紹介 生成完了")

    return {
        "series_meta": series_meta,
        "episodes": episodes,
        "characters": characters,
    }
