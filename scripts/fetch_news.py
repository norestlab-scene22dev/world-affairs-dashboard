#!/usr/bin/env python3
"""
fetch_news.py
戦略17分野に関する国内外ニュースを自動収集し、data/news.json に出力する。

収集元:
  1. Google News RSS (分野ごとのキーワード検索。日本語・英語の両方でクエリを投げるため、
     海外ニュースも含めて網羅的に拾える)
  2. 主要金融メディアの一般RSS（キーワードマッチで分野に自動分類。どの分野にも
     マッチしない場合は general バケツに入る）

APIキーは不要。Google News RSS は誰でも無料で利用可能。
英語記事のタイトルは deep-translator（Google翻訳の無料エンドポイント。APIキー不要）で
自動的に日本語へ翻訳し、title_ja フィールドに保存する。翻訳に失敗しても処理は継続する。

使い方:
  python scripts/fetch_news.py
  python scripts/fetch_news.py --per-sector 5   # 分野・言語ごとの取得件数を変更
  python scripts/fetch_news.py --no-translate   # 翻訳をスキップして高速化
"""

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

import feedparser

ROOT = Path(__file__).resolve().parent.parent
SECTORS_PATH = ROOT / "data" / "sectors.json"
OUTPUT_PATH = ROOT / "data" / "news.json"

TRANSLATE_SLEEP_SEC = 0.3  # 翻訳API(無料エンドポイント)への負荷軽減用ウェイト
RETENTION_DAYS = 4  # これより古い記事(published基準)は削除する

# 分野横断で拾う一般ニュースRSS（キーワードで分野に自動分類される）
GENERAL_FEEDS = [
    {"name": "Yahoo Finance (Top News)", "url": "https://finance.yahoo.com/news/rssindex", "lang": "en"},
    {"name": "MarketWatch (Top Stories)", "url": "http://feeds.marketwatch.com/marketwatch/topstories/", "lang": "en"},
    {"name": "CNBC (Markets)", "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html", "lang": "en"},
    {"name": "Nikkei Asia (Business)", "url": "https://asia.nikkei.com/rss/feed/nar", "lang": "en"},
    {"name": "NHK News (Business)", "url": "https://www.nhk.or.jp/rss/news/cat5.xml", "lang": "ja"},
]

GOOGLE_NEWS_TEMPLATE_JA = "https://news.google.com/rss/search?q={query}+when:2d&hl=ja&gl=JP&ceid=JP:ja"
GOOGLE_NEWS_TEMPLATE_EN = "https://news.google.com/rss/search?q={query}+when:2d&hl=en-US&gl=US&ceid=US:US"

REQUEST_SLEEP_SEC = 0.5  # Google News に負荷をかけすぎないためのウェイト


def load_sectors():
    with open(SECTORS_PATH, encoding="utf-8") as f:
        return json.load(f)["sectors"]


def build_query(keywords, max_terms=4):
    """キーワードリストから Google News 検索クエリ文字列(OR連結)を作る"""
    terms = keywords[:max_terms]
    quoted = [f'"{t}"' if " " in t else t for t in terms]
    query = " OR ".join(quoted)
    return urllib.parse.quote(query)


def fetch_feed(url, retries=2):
    for attempt in range(retries):
        try:
            feed = feedparser.parse(url)
            if feed.entries or attempt == retries - 1:
                return feed
        except Exception as e:
            print(f"  ! フィード取得失敗 ({url}): {e}", file=sys.stderr)
        time.sleep(1)
    return feedparser.parse(url)


def normalize_entry(entry, source_name, sector_id, lang="ja"):
    title = getattr(entry, "title", "").strip()
    link = getattr(entry, "link", "")
    summary = re.sub("<[^<]+?>", "", getattr(entry, "summary", "")).strip()[:300]
    published = getattr(entry, "published", None) or getattr(entry, "updated", None)
    try:
        published_parsed = getattr(entry, "published_parsed", None)
        if published_parsed:
            published_iso = dt.datetime(*published_parsed[:6], tzinfo=dt.timezone.utc).isoformat()
        else:
            published_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    except Exception:
        published_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    return {
        "sector_id": sector_id,
        "title": title,
        "link": link,
        "source": source_name,
        "published": published_iso,
        "summary": summary,
        "lang": lang,
    }


def classify_generic_entry(title, summary, sectors):
    """一般フィードの記事をキーワードマッチで分野に分類。マッチしなければ None"""
    text = f"{title} {summary}".lower()
    best_sector = None
    best_hits = 0
    for sector in sectors:
        keywords = sector["keywords_ja"] + sector["keywords_en"]
        hits = sum(1 for kw in keywords if kw.lower() in text)
        if hits > best_hits:
            best_hits = hits
            best_sector = sector["id"]
    return best_sector if best_hits > 0 else None


def collect_sector_news(sectors, per_sector):
    items = []
    seen_links = set()

    for sector in sectors:
        sector_id = sector["id"]
        print(f"[{sector_id}] {sector['name_ja']} のニュースを取得中...")

        query_ja = build_query(sector["keywords_ja"])
        query_en = build_query(sector["keywords_en"])

        for lang, template, query in [
            ("ja", GOOGLE_NEWS_TEMPLATE_JA, query_ja),
            ("en", GOOGLE_NEWS_TEMPLATE_EN, query_en),
        ]:
            url = template.format(query=query)
            feed = fetch_feed(url)
            count = 0
            for entry in feed.entries:
                if count >= per_sector:
                    break
                link = getattr(entry, "link", "")
                if not link or link in seen_links:
                    continue
                seen_links.add(link)
                source_name = getattr(getattr(entry, "source", None), "title", None) or (
                    "Google News (JP)" if lang == "ja" else "Google News (EN)"
                )
                items.append(normalize_entry(entry, source_name, sector_id, lang=lang))
                count += 1
            time.sleep(REQUEST_SLEEP_SEC)

    return items, seen_links


def collect_general_news(sectors, seen_links):
    items = []
    for feed_info in GENERAL_FEEDS:
        print(f"[general] {feed_info['name']} を取得中...")
        feed = fetch_feed(feed_info["url"])
        for entry in feed.entries[:20]:
            link = getattr(entry, "link", "")
            if not link or link in seen_links:
                continue
            title = getattr(entry, "title", "")
            summary = re.sub("<[^<]+?>", "", getattr(entry, "summary", ""))
            sector_id = classify_generic_entry(title, summary, sectors)
            if sector_id is None:
                continue  # どの戦略分野にも該当しない一般ニュースは除外
            seen_links.add(link)
            items.append(normalize_entry(entry, feed_info["name"], sector_id, lang=feed_info.get("lang", "ja")))
    return items

def load_existing_items():
    """前回実行時の news.json を読み込む。無い/壊れている場合は空リストを返す。"""
    if not OUTPUT_PATH.exists():
        return []
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("items", [])
    except Exception as e:
        print(f"! 既存news.jsonの読み込みに失敗しました: {e}", file=sys.stderr)
        return []


def prune_old_items(items, days=RETENTION_DAYS):
    """published が days日より前の記事を取り除く。日付が壊れている記事は念のため残す。"""
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    pruned = []
    for it in items:
        try:
            published = dt.datetime.fromisoformat(it["published"])
        except Exception:
            pruned.append(it)
            continue
        if published >= cutoff:
            pruned.append(it)
    return pruned
def translate_items(items):
    """lang == 'en' の記事タイトルを日本語に翻訳し、title_ja に格納する。
    deep-translator が未インストール、またはネットワークエラー時は静かにスキップする。"""
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        print("! deep-translator が見つからないため翻訳をスキップします（pip install deep-translator）", file=sys.stderr)
        return items

    translator = GoogleTranslator(source="en", target="ja")
    en_items = [it for it in items if it.get("lang") == "en" and it.get("title")]
    print(f"英語記事 {len(en_items)}件を日本語に翻訳中...")

    for i, item in enumerate(en_items):
        try:
            item["title_ja"] = translator.translate(item["title"])
        except Exception as e:
            print(f"  ! 翻訳失敗 ({item['title'][:50]}...): {e}", file=sys.stderr)
        time.sleep(TRANSLATE_SLEEP_SEC)
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(en_items)}件 翻訳完了")

    return items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-sector", type=int, default=6, help="分野・言語ごとの取得件数")
    parser.add_argument("--no-translate", action="store_true", help="英語記事タイトルの日本語翻訳をスキップする")
    args = parser.parse_args()

    sectors = load_sectors()

    sector_items, seen_links = collect_sector_news(sectors, args.per_sector)
    general_items = collect_general_news(sectors, seen_links)
    fetched_items = sector_items + general_items

    existing_items = load_existing_items()
    existing_links = {it.get("link") for it in existing_items}

    # 既存に無い、本当に新しい記事だけを翻訳・追加対象にする（既存記事は再翻訳しない）
    new_items = [it for it in fetched_items if it.get("link") not in existing_links]
    print(f"新規記事: {len(new_items)}件（既存 {len(existing_items)}件とマージします）")

    if not args.no_translate:
        new_items = translate_items(new_items)

    all_items = existing_items + new_items
    all_items = prune_old_items(all_items)
    all_items.sort(key=lambda x: x["published"], reverse=True)

    output = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "count": len(all_items),
        "items": all_items,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n完了: {len(all_items)}件のニュースを {OUTPUT_PATH} に保存しました。")


if __name__ == "__main__":
    main()