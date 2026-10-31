# 商社就活ニュース アプリ

7大総合商社と主要な専門商社のニュースを自動で集め、重複をまとめ、ハッシュタグを付けて、
スマホから読めるようにする個人用アプリです。

- **自動収集**：各社ごとにニュースを取得（Google ニュースの検索フィード）
- **重複除去**：同じニュースが複数メディアから出ても1件にまとめる
- **自動タグ付け**：`#決算` `#脱炭素` `#M&A` などを自動で付与。タグをタップで絞り込み
- **AI要約**：記事の要点を1〜2文で表示（任意。APIキーを登録したときだけ有効）
- **会社別の絞り込み**：総合／専門／各社ごとに表示
- **検索**：社名・事業・メディア名で全文検索
- **スマホ対応**：ホーム画面に追加してアプリのように使える（PWA）

---

## 対象企業

**総合商社（7社）**：三菱商事／三井物産／伊藤忠商事／住友商事／丸紅／豊田通商／双日
**専門商社**：兼松／伊藤忠丸紅鉄鋼／長瀬産業／メタルワン／JFE商事

企業の追加・削除は `collect.py` の `COMPANIES` を編集するだけです（やり方は依頼してください）。

---

## 仕組み（なぜ無料でスマホから見られるのか）

```
GitHub Actions（1日3回 自動実行）
   └─ collect.py が各社ニュースを収集・タグ付け・要約
        └─ data/news.json を更新してコミット
GitHub Pages（無料の公開場所）
   └─ index.html が news.json を読み込んでスマホに表示
```

サーバーを借りる必要はありません。すべて GitHub の無料枠で完結します。

---

## セットアップ手順（開発経験ゼロでも進められます）

> 画面を見ながら一緒に進められます。つまずいたらそのまま質問してください。

### 1. GitHub アカウントを作る
https://github.com で無料登録（メールアドレスだけでOK）。

### 2. リポジトリ（置き場所）を作る
- 右上の「＋」→「New repository」
- Repository name：`shosha-news`
- 「Public」を選ぶ（Pages を無料で使うため）
- 「Create repository」

### 3. ファイルを置く
このフォルダ一式（`index.html` などすべて）を、作ったリポジトリにアップロードします。
- リポジトリ画面の「Add file」→「Upload files」
- フォルダの中身をドラッグ＆ドロップ →「Commit changes」

### 4. GitHub Pages を有効にする（＝公開）
- リポジトリの「Settings」→ 左メニュー「Pages」
- 「Build and deployment」の Source を **Deploy from a branch**
- Branch を **main** ／ フォルダは **/(root)** →「Save」
- 1〜2分すると、画面上部に公開URL（`https://ユーザー名.github.io/shosha-news/`）が出ます
  → これをスマホのブラウザで開けばアプリが見られます

### 5. 自動更新をオンにする
- リポジトリの「Actions」タブを開く →「I understand my workflows, go ahead and enable them」
- これで1日3回、自動でニュースが更新されます
- すぐ試したいときは「Actions」→「ニュース収集」→「Run workflow」で手動実行できます

### 6. （任意）AI要約をオンにする
AI要約を使う場合のみ。使わなくてもアプリは動きます。
- Anthropic の API キーを用意（https://console.anthropic.com ）
- リポジトリの「Settings」→「Secrets and variables」→「Actions」→「New repository secret」
- Name：`ANTHROPIC_API_KEY`／Secret：取得したキー →「Add secret」
- 次回の自動実行から要約が付きます（料金は使った分だけ。安価なモデルを使用）

### 7. スマホのホーム画面に追加
- 公開URLをスマホで開く
- iPhone（Safari）：共有ボタン →「ホーム画面に追加」
- Android（Chrome）：メニュー →「アプリをインストール」/「ホーム画面に追加」

---

## 手元のPCで試す（任意）

```bash
pip install -r requirements.txt
python collect.py          # data/news.json を更新
# 画面確認（簡易サーバー）
python -m http.server 8000 # ブラウザで http://localhost:8000
```

`index.html` をそのままダブルクリックして開いた場合は、サンプルデータが表示されます。

---

## 設定を変えたいとき（`collect.py`）

| 変えたいこと | 場所 |
|---|---|
| 企業を追加・削除 | `COMPANIES` |
| タグの種類・判定キーワード | `TAG_RULES` |
| 保持する記事の最大数 | `MAX_ARTICLES` |
| 1社あたりの取得件数 | `PER_COMPANY_LIMIT` |
| AI要約のモデル | 環境変数 `ANTHROPIC_MODEL` |

編集に不安があれば、変えたい内容を伝えてくれればこちらで修正します。
