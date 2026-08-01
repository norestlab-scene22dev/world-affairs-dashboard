# 世界情勢 × 成長産業ダッシュボード

日本政府「日本成長戦略」の**戦略17分野**（AI・半導体、量子、航空・宇宙、創薬・先端医療、コンテンツ 等）を軸に、
国内外のニュースと関連銘柄の株価を横断的にキャッチアップするためのローカルWebダッシュボードです。

- ニュース収集元: METI（経済産業省）・内閣官房の政策情報をベースにした分野定義 + Google News RSS（日本語・英語の両方でクエリするため海外ニュースも拾えます）+ 主要金融メディアRSS
- 株価取得: [yfinance](https://github.com/ranaroussi/yfinance)（APIキー不要）
- 表示: 単一HTMLファイル（`index.html`）。JSONを読み込んで描画するだけなので、サーバー不要でVSCode上でそのまま編集できます。

## ディレクトリ構成

```
world-affairs-dashboard/
├── index.html              # ダッシュボード本体（このファイルをブラウザで開く）
├── requirements.txt         # Python依存パッケージ
├── data/
│   ├── sectors.json         # 戦略17分野の定義（キーワード・代表銘柄。自由に編集可）
│   ├── news.json            # fetch_news.py の出力（自動生成）
│   └── stocks.json          # fetch_stocks.py の出力（自動生成）
└── scripts/
    ├── fetch_news.py        # ニュース自動収集
    └── fetch_stocks.py      # 株価自動取得
```

## セットアップ（VSCode）

1. このフォルダを VSCode で開く（`File > Open Folder...`）
2. ターミナルを開き、仮想環境を作成して依存パッケージをインストール

   ```bash
   python3 -m venv venv
   source venv/bin/activate        # Windowsは venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. ニュースと株価を取得

   ```bash
   python scripts/fetch_news.py
   python scripts/fetch_stocks.py
   ```

   `data/news.json` と `data/stocks.json` が生成されます。

4. ダッシュボードを表示

   ブラウザの `fetch()` はセキュリティ上 `file://` から直接JSONを読み込めないため、簡易サーバーを立てて開いてください。

   ```bash
   python -m http.server 8000
   ```

   その後ブラウザで `http://localhost:8000/index.html` を開く。
   （VSCode拡張機能の "Live Server" を使ってもOKです）

## 使い方

- 左サイドバーに戦略17分野が並びます。デフォルトは「株価インパクト順」（分野内の代表銘柄の平均騰落率の絶対値が大きい順）。「分野名順」「自己評価順」にも切り替え可能。
- 分野をクリックすると、その分野の代表銘柄の株価と関連ニュース一覧が表示されます。
- 各分野には「成長株4条件」（①市場成長性 ②市場シェア ③参入障壁 ④マネタイズ力）を1〜5で自己評価できるパネルがあります。評価はブラウザのlocalStorageに自動保存されます（サーバー送信なし）。
- トップ画面（分野未選択時）は「株価インパクト上位分野」と「全分野横断の最新ニュース」を表示します。

## 更新の自動化

日次で最新化したい場合は、`cron`（Mac/Linux）や タスクスケジューラ（Windows）で下記を定期実行してください。

```bash
cd /path/to/world-affairs-dashboard && \
  venv/bin/python scripts/fetch_news.py && \
  venv/bin/python scripts/fetch_stocks.py
```

例: 毎朝7時に実行する crontab エントリ

```
0 7 * * * cd /path/to/world-affairs-dashboard && venv/bin/python scripts/fetch_news.py && venv/bin/python scripts/fetch_stocks.py
```

## カスタマイズ

- **分野・キーワード・銘柄の追加/変更**: `data/sectors.json` を直接編集してください。`keywords_ja` / `keywords_en` はニュース検索クエリに、`tickers` は株価取得（yfinance形式。日本株は `xxxx.T`）に使われます。
- **取得件数の変更**: `python scripts/fetch_news.py --per-sector 10` のように引数で調整可能（デフォルト6件/分野/言語）。
- **ニュースソースの追加**: `scripts/fetch_news.py` の `GENERAL_FEEDS` リストにRSS URLを追加すると、キーワードマッチで自動的に分野分類されます。

## 注意事項

- Google News RSS・各社RSSの仕様変更により、取得できなくなる場合があります。エラーはターミナルに警告として表示されますが、他のフィードの取得は継続されます。
- 本ダッシュボードの株価・ニュースは投資助言ではありません。最終的な投資判断はご自身の責任で行ってください。
- yfinanceはYahoo Financeの非公式APIラッパーのため、将来的に仕様変更で動作しなくなる可能性があります。その際はバージョンアップ（`pip install -U yfinance`）をお試しください。
