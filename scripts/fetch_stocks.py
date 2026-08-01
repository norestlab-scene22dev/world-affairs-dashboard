#!/usr/bin/env python3
"""
fetch_stocks.py
戦略17分野の代表銘柄の株価(現在値・前日比騰落率)を取得し、data/stocks.json に出力する。

yfinance を利用（APIキー不要）。ダッシュボード側はこの騰落率を使って
「直近で株価インパクトが大きい分野」を上位に絞り込み表示する。

使い方:
  python scripts/fetch_stocks.py
"""

import datetime as dt
import json
import sys
import time
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
SECTORS_PATH = ROOT / "data" / "sectors.json"
OUTPUT_PATH = ROOT / "data" / "stocks.json"


def load_sectors():
    with open(SECTORS_PATH, encoding="utf-8") as f:
        return json.load(f)["sectors"]


def fetch_ticker_data(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist.empty or len(hist) < 2:
            hist = t.history(period="1mo")
        if hist.empty:
            return None
        last_close = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else last_close
        change_pct = ((last_close - prev_close) / prev_close * 100) if prev_close else 0.0
        try:
            fast_info = t.fast_info
            currency = getattr(fast_info, "currency", None) or fast_info.get("currency", "")
        except Exception:
            currency = ""
        # 会社名（表示用）。取得に失敗した場合はティッカーをそのまま使う
        info_name = ticker
        try:
            info = t.info
            info_name = info.get("shortName") or info.get("longName") or ticker
        except Exception:
            pass
        return {
            "ticker": ticker,
            "name": info_name,
            "price": round(last_close, 2),
            "change_pct": round(change_pct, 2),
            "currency": currency,
        }
    except Exception as e:
        print(f"  ! {ticker} の取得失敗: {e}", file=sys.stderr)
        return None


def main():
    sectors = load_sectors()
    sector_results = []

    # 銘柄取得を重複排除しつつキャッシュ
    ticker_cache = {}

    for sector in sectors:
        print(f"[{sector['id']}] {sector['name_ja']} の株価を取得中...")
        stocks = []
        for ticker in sector["tickers"]:
            if ticker not in ticker_cache:
                ticker_cache[ticker] = fetch_ticker_data(ticker)
                time.sleep(0.3)
            data = ticker_cache[ticker]
            if data:
                stocks.append(data)

        avg_change = (
            round(sum(s["change_pct"] for s in stocks) / len(stocks), 2) if stocks else None
        )
        sector_results.append(
            {
                "sector_id": sector["id"],
                "name_ja": sector["name_ja"],
                "stocks": stocks,
                "avg_change_pct": avg_change,
            }
        )

    sector_results.sort(
        key=lambda s: abs(s["avg_change_pct"]) if s["avg_change_pct"] is not None else -1,
        reverse=True,
    )

    output = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sectors": sector_results,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n完了: {len(sector_results)}分野の株価データを {OUTPUT_PATH} に保存しました。")


if __name__ == "__main__":
    main()
