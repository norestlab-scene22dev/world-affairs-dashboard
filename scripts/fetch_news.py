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

使い方:
  python scripts/fetch_news.py
  python scripts/fetch_news.py --per-sector 5   # 分野・言語ごとの取得件数を変更
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


def normalize_entry(entry, source_name, sector_id):
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
                items.append(normalize_entry(entry, source_name, sector_id))
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
            items.append(normalize_entry(entry, feed_info["name"], sector_id))
    return items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-sector", type=int, default=6, help="分野・言語ごとの取得件数")
    args = parser.parse_args()

    sectors = load_sectors()

    sector_items, seen_links = collect_sector_news(sectors, args.per_sector)
    general_items = collect_general_news(sectors, seen_links)

    all_items = sector_items + general_items
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
