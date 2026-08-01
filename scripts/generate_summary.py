#!/usr/bin/env python3
"""
generate_summary.py
data/news.json・data/stocks.json・data/sectors.json を読み込み、
その日のキーワード集計サマリを data/summary.json に出力する。

AI・外部APIは使わず、キーワード頻度と件数の集計のみでサマリ文を生成する。

使い方:
  python scripts/generate_summary.py
"""

import datetime as dt
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECTORS_PATH = ROOT / "data" / "sectors.json"
NEWS_PATH = ROOT / "data" / "news.json"
STOCKS_PATH = ROOT / "data" / "stocks.json"
OUTPUT_PATH = ROOT / "data" / "summary.json"

LOOKBACK_HOURS = 30  # 「本日」とみなす直近何時間分のニュースを集計対象にするか


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def within_lookback(iso_str, now, hours):
    try:
        t = dt.datetime.fromisoformat(iso_str)
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return False
    return (now - t).total_seconds() <= hours * 3600


def top_keywords_for_sector(items, sector_def, limit=5):
    keywords = sector_def.get("keywords_ja", []) + sector_def.get("keywords_en", [])
    counter = Counter()
    for item in items:
        text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        for kw in keywords:
            if kw.lower() in text:
                counter[kw] += 1
    return [kw for kw, _ in counter.most_common(limit)]


def main():
    sectors = load_json(SECTORS_PATH, {"sectors": []})["sectors"]
    news = load_json(NEWS_PATH, {"items": []})
    stocks = load_json(STOCKS_PATH, {"sectors": []})

    now = dt.datetime.now(dt.timezone.utc)
    recent_items = [n for n in news.get("items", []) if within_lookback(n.get("published", ""), now, LOOKBACK_HOURS)]
    if not recent_items:
        recent_items = news.get("items", [])

    items_by_sector = {}
    for item in recent_items:
        items_by_sector.setdefault(item["sector_id"], []).append(item)

    stock_map = {s["sector_id"]: s for s in stocks.get("sectors", [])}

    sector_summaries = []
    for sector in sectors:
        sid = sector["id"]
        sector_items = items_by_sector.get(sid, [])
        stock_info = stock_map.get(sid, {})
        article_count = len(sector_items)
        avg_change_pct = stock_info.get("avg_change_pct")
        top_keywords = top_keywords_for_sector(sector_items, sector)

        # 分野ごとの短い見出し文（AI不使用・テンプレートベース）
        parts = [f"直近{LOOKBACK_HOURS}時間で{article_count}件のニュースを検出。"]
        if top_keywords:
            parts.append(f"話題のキーワード: {'、'.join(top_keywords)}。")
        if avg_change_pct is not None:
            parts.append(f"代表銘柄の平均株価は前日比{avg_change_pct:+.1f}%。")
        sector_headline = " ".join(parts)

        sector_summaries.append({
            "sector_id": sid,
            "name_ja": sector["name_ja"],
            "article_count": article_count,
            "avg_change_pct": avg_change_pct,
            "top_keywords": top_keywords,
            "top_titles": [it["title"] for it in sector_items[:3]],
            "headline": sector_headline,
        })

    by_count = sorted(sector_summaries, key=lambda s: s["article_count"], reverse=True)
    top_count_sectors = [s for s in by_count if s["article_count"] > 0][:3]

    by_impact = sorted(
        [s for s in sector_summaries if s["avg_change_pct"] is not None],
        key=lambda s: abs(s["avg_change_pct"]),
        reverse=True,
    )
    top_impact_sectors = by_impact[:3]

    total_articles = len(recent_items)

    headline_parts = [f"直近{LOOKBACK_HOURS}時間で{total_articles}件のニュースを検出。"]
    if top_count_sectors:
        top_str = "、".join(f"{s['name_ja']}({s['article_count']}件)" for s in top_count_sectors)
        headline_parts.append(f"報道量が多い分野は{top_str}。")
    if top_impact_sectors:
        impact_str = "、".join(
            f"{s['name_ja']}({s['avg_change_pct']:+.1f}%)" for s in top_impact_sectors
        )
        headline_parts.append(f"株価インパクトが大きい分野は{impact_str}。")

    output = {
        "generated_at": now.isoformat(),
        "lookback_hours": LOOKBACK_HOURS,
        "total_articles": total_articles,
        "headline": " ".join(headline_parts),
        "top_count_sectors": [s["sector_id"] for s in top_count_sectors],
        "top_impact_sectors": [s["sector_id"] for s in top_impact_sectors],
        "sectors": sector_summaries,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"完了: サマリを {OUTPUT_PATH} に保存しました。")
    print(output["headline"])


if __name__ == "__main__":
    main()
