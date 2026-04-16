# メンエス好きのアシタカマガジン

メンズエステの最新情報、厳選レビュー、おすすめ店舗ガイドを提供する情報メディアサイトです。

## サイト構成

- **トップページ** (`index.html`) — 最新記事・おすすめ店舗
- **記事一覧** (`articles/index.html`) — ブログ記事の一覧
- **店舗紹介** (`shops/index.html`) — メンズエステ店舗の一覧
- **About** (`about/index.html`) — サイトについて

## データ管理

記事と店舗の情報はJSONファイルで管理しています。

- `data/articles.json` — 記事データ
- `data/shops.json` — 店舗データ

## ビルド

```bash
python3 build.py
```

`public/` ディレクトリにデプロイ用ファイルが生成されます。

## デプロイ

GitHub Pagesで自動デプロイ。`main` ブランチにpushすると自動的にビルド＆デプロイされます。

## 記事の追加方法

1. `data/articles.json` に記事データを追加
2. `git commit` & `git push`
3. GitHub Actionsが自動でビルド＆デプロイ

### 記事データの形式

```json
{
  "slug": "article-url-slug",
  "title": "記事タイトル",
  "date": "2026-04-15",
  "area": "東京都",
  "excerpt": "記事の概要文",
  "content": "<p>記事の本文HTML</p>",
  "wakust_url": "https://wakust.com/...",
  "thumbnail": ""
}
```

## カスタムドメイン

`menesthe-ashitaka.com` で公開。DNS設定はGitHub Pagesのドキュメントを参照。
