from dotenv import load_dotenv
load_dotenv()
import argparse
import os
from datetime import datetime, timedelta
from typing import List

import requests
import yfinance as yf


FINNHUB_KEY = os.getenv("FINNHUB_KEY", "")


def _headline_key(text: str) -> str:
    if not text:
        return ""
    return "".join(text.lower().split())[:80]


def _fetch_finnhub_headlines(ticker: str, news_from: str, news_to: str, limit: int = 30) -> list:
    if not FINNHUB_KEY:
        return []
    try:
        news_resp = requests.get(
            "https://finnhub.io/api/v1/company-news",
            params={
                "symbol": ticker,
                "from": news_from,
                "to": news_to,
                "token": FINNHUB_KEY,
            },
            timeout=12,
        )
        if not news_resp.ok:
            return []
        out = []
        for item in news_resp.json()[:limit]:
            out.append(
                {
                    "headline": item.get("headline"),
                    "summary": (item.get("summary") or "")[:400],
                    "datetime": item.get("datetime"),
                    "source": item.get("source"),
                    "url": item.get("url"),
                }
            )
        return out
    except requests.RequestException:
        return []


def _fetch_yfinance_headlines(ticker: str, target: datetime, days_back: int = 7) -> list:
    """Supplement Finnhub with Yahoo Finance ticker news when available."""
    try:
        stock = yf.Ticker(ticker)
        raw = getattr(stock, "news", None) or []
    except Exception:
        return []
    if not raw:
        return []
    out = []
    for item in raw[:40]:
        title = item.get("title") or item.get("headline")
        if not title:
            continue
        ts = item.get("providerPublishTime")
        if ts is None:
            continue
        if ts > 1e12:
            ts = int(ts / 1000)
        pub = datetime.utcfromtimestamp(int(ts)).date()
        if not ((target - timedelta(days=days_back)).date() <= pub <= (target + timedelta(days=1)).date()):
            continue
        out.append(
            {
                "headline": title,
                "summary": "",
                "datetime": int(ts),
                "source": item.get("publisher") or "Yahoo Finance",
                "url": item.get("link"),
            }
        )
    return out[:20]


def _merge_headlines(primary: list, secondary: list) -> list:
    seen = set()
    merged = []
    for batch in (primary, secondary):
        for h in batch:
            hl = h.get("headline") or ""
            k = _headline_key(hl)
            if not k or k in seen:
                continue
            seen.add(k)
            merged.append(h)
    return merged


def fetch_stock_context(ticker: str, date: str) -> dict:
    """
    Returns a structured dict of everything needed to explain a stock move.
    date format: 'YYYY-MM-DD'
    """
    target = datetime.strptime(date, "%Y-%m-%d")
    start = (target - timedelta(days=10)).strftime("%Y-%m-%d")
    end = (target + timedelta(days=1)).strftime("%Y-%m-%d")

    stock = yf.Ticker(ticker)
    spy = yf.Ticker("SPY")

    # --- Price data ---
    hist = stock.history(start=start, end=end)
    spy_hist = spy.history(start=start, end=end)

    target_row = hist[hist.index.date == target.date()]
    prev_row = hist[hist.index.date < target.date()].tail(1)

    price_change_pct = None
    volume_vs_avg = None
    if not target_row.empty and not prev_row.empty:
        close = float(target_row["Close"].iloc[0])
        prev_close = float(prev_row["Close"].iloc[0])
        price_change_pct = round((close - prev_close) / prev_close * 100, 2)

        avg_vol = float(hist["Volume"].mean()) if not hist.empty else 0.0
        day_vol = float(target_row["Volume"].iloc[0])
        volume_vs_avg = round(day_vol / avg_vol, 2) if avg_vol > 0 else None

    # Market move on same day
    spy_row = spy_hist[spy_hist.index.date == target.date()]
    spy_prev = spy_hist[spy_hist.index.date < target.date()].tail(1)
    market_change_pct = None
    if not spy_row.empty and not spy_prev.empty:
        market_change_pct = round(
            (float(spy_row["Close"].iloc[0]) - float(spy_prev["Close"].iloc[0]))
            / float(spy_prev["Close"].iloc[0])
            * 100,
            2,
        )

    # --- News (wider window for daily context; Finnhub + Yahoo supplement) ---
    news_from = (target - timedelta(days=7)).strftime("%Y-%m-%d")
    news_to = (target + timedelta(days=1)).strftime("%Y-%m-%d")
    fh = _fetch_finnhub_headlines(ticker, news_from, news_to, limit=35)
    yf_news = _fetch_yfinance_headlines(ticker, target, days_back=7)
    headlines = _merge_headlines(fh, yf_news)

    # --- Earnings ---
    recent_earnings = None
    if FINNHUB_KEY:
        try:
            earnings_resp = requests.get(
                "https://finnhub.io/api/v1/stock/earnings",
                params={"symbol": ticker, "token": FINNHUB_KEY},
                timeout=10,
            )
            if earnings_resp.ok:
                for e in earnings_resp.json():
                    period = e.get("period")
                    if not period:
                        continue
                    e_date = datetime.strptime(period, "%Y-%m-%d")
                    if abs((e_date - target).days) <= 5:
                        recent_earnings = {
                            "period": period,
                            "actual": e.get("actual"),
                            "estimate": e.get("estimate"),
                            "surprise_pct": e.get("surprisePercent"),
                        }
                        break
        except requests.RequestException:
            pass

    # --- Analyst recommendations ---
    latest_rec = None
    if FINNHUB_KEY:
        try:
            rec_resp = requests.get(
                "https://finnhub.io/api/v1/stock/recommendation",
                params={"symbol": ticker, "token": FINNHUB_KEY},
                timeout=10,
            )
            if rec_resp.ok:
                rec_data = rec_resp.json()
                latest_rec = rec_data[0] if rec_data else None
        except requests.RequestException:
            pass

    return {
        "ticker": ticker,
        "date": date,
        "price_change_pct": price_change_pct,
        "volume_vs_avg": volume_vs_avg,
        "market_change_pct": market_change_pct,
        "idiosyncratic_move": round(price_change_pct - market_change_pct, 2)
        if price_change_pct is not None and market_change_pct is not None
        else None,
        "headlines": headlines,
        "earnings": recent_earnings,
        "analyst_rec": latest_rec,
    }


def explain_move_paragraph(context: dict) -> str:
    """
    Convert fetch_stock_context output into a single human-readable paragraph.
    """
    ticker = context.get("ticker", "UNKNOWN")
    date = context.get("date", "")
    price_change = context.get("price_change_pct")
    market_change = context.get("market_change_pct")
    idio = context.get("idiosyncratic_move")
    volume_vs_avg = context.get("volume_vs_avg")
    earnings = context.get("earnings")
    headlines = context.get("headlines") or []
    analyst_rec = context.get("analyst_rec")

    try:
        pretty_date = datetime.strptime(date, "%Y-%m-%d").strftime("%b %d, %Y")
    except Exception:
        pretty_date = date

    if price_change is None:
        return (
            f"{ticker} on {pretty_date}: no valid trading data was found for that date, "
            "so a move explanation cannot be determined (market holiday, weekend, or missing data)."
        )

    direction = "rose" if price_change > 0 else "fell" if price_change < 0 else "was flat"
    lead = (
        f"On {pretty_date}, {ticker} was flat (0.00%)."
        if direction == "was flat"
        else f"On {pretty_date}, {ticker} {direction} {abs(price_change):.2f}%."
    )
    parts = [lead]

    if market_change is not None:
        m_dir = "rose" if market_change > 0 else "fell" if market_change < 0 else "was flat"
        if m_dir == "was flat":
            parts.append("The broader market (SPY) was flat.")
        else:
            parts.append(f"The broader market (SPY) {m_dir} {abs(market_change):.2f}%.")

    if idio is not None:
        if abs(idio) < 0.5:
            parts.append(
                "This suggests the move was largely market-driven with limited stock-specific divergence."
            )
        elif idio > 0:
            parts.append(
                f"The stock outperformed the market by {abs(idio):.2f}%, pointing to company-specific strength."
            )
        else:
            parts.append(
                f"The stock underperformed the market by {abs(idio):.2f}%, pointing to company-specific weakness."
            )

    if volume_vs_avg is not None:
        if volume_vs_avg >= 1.5:
            parts.append(
                f"Trading volume was elevated at {volume_vs_avg:.2f}x its average, adding conviction to the move."
            )
        elif volume_vs_avg <= 0.7:
            parts.append(
                f"Trading volume was light at {volume_vs_avg:.2f}x average, so conviction behind the move may be weaker."
            )
        else:
            parts.append(f"Volume was near normal at {volume_vs_avg:.2f}x average.")

    if earnings:
        period = earnings.get("period")
        actual = earnings.get("actual")
        estimate = earnings.get("estimate")
        surprise = earnings.get("surprise_pct")
        parts.append(
            f"A nearby earnings report may have been a catalyst (period {period}, actual {actual}, estimate {estimate}, surprise {surprise}%)."
        )

    if headlines:
        top_headlines = [h.get("headline") for h in headlines[:5] if h.get("headline")]
        if top_headlines:
            shown = " | ".join(top_headlines[:3])
            if len(top_headlines) > 3:
                shown += f" (+{len(top_headlines) - 3} more in news list)"
            parts.append(f"Recent company news likely in focus: {shown}.")

    if analyst_rec:
        period = analyst_rec.get("period")
        strong_buy = analyst_rec.get("strongBuy", 0)
        buy = analyst_rec.get("buy", 0)
        hold = analyst_rec.get("hold", 0)
        sell = analyst_rec.get("sell", 0)
        strong_sell = analyst_rec.get("strongSell", 0)
        parts.append(
            f"Analyst recommendations ({period}) were SB:{strong_buy}, B:{buy}, H:{hold}, S:{sell}, SS:{strong_sell}, which provides additional sentiment context."
        )

    if earnings and abs(price_change) >= 2:
        parts.append(
            "Overall, the move appears primarily earnings-driven, with macro conditions as a secondary influence."
        )
    elif headlines and abs(price_change) >= 1:
        parts.append("Overall, the move appears primarily tied to company-specific news flow.")
    elif idio is not None and abs(idio) < 0.5:
        parts.append(
            "Overall, this looks mostly like a macro/market move rather than a company-specific repricing."
        )
    else:
        parts.append(
            "Overall, the move likely reflects a combination of market backdrop and stock-specific factors."
        )

    return " ".join(parts)


def mock_context(ticker: str, date: str) -> dict:
    return {
        "ticker": ticker.upper(),
        "date": date,
        "price_change_pct": 3.42,
        "volume_vs_avg": 1.87,
        "market_change_pct": 0.78,
        "idiosyncratic_move": 2.64,
        "headlines": [
            {"headline": "Company beats earnings expectations", "summary": "", "datetime": 0},
            {"headline": "Guidance raised for next quarter", "summary": "", "datetime": 0},
        ],
        "earnings": {
            "period": "2025-09-30",
            "actual": 1.64,
            "estimate": 1.52,
            "surprise_pct": 7.89,
        },
        "analyst_rec": {
            "period": "2025-10-01",
            "strongBuy": 12,
            "buy": 18,
            "hold": 7,
            "sell": 1,
            "strongSell": 0,
        },
    }


def parse_tickers_input(value: str) -> List[str]:
    """
    Parse comma-separated tickers into a deduplicated uppercase list.
    Example: "AAPL, msft, TSLA" -> ["AAPL", "MSFT", "TSLA"]
    """
    raw = [item.strip().upper() for item in value.split(",")]
    cleaned = [item for item in raw if item]
    # Preserve input order while removing duplicates.
    return list(dict.fromkeys(cleaned))


def parse_dates_input(value: str) -> List[str]:
    """
    Parse comma-separated dates into a deduplicated YYYY-MM-DD list.
    """
    raw = [item.strip() for item in value.split(",")]
    cleaned = [item for item in raw if item]
    # Validate each date early and keep normalized format.
    normalized = []
    for item in cleaned:
        normalized_date = datetime.strptime(item, "%Y-%m-%d").strftime("%Y-%m-%d")
        normalized.append(normalized_date)
    return list(dict.fromkeys(normalized))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Explain why a stock moved on a given date.")
    parser.add_argument(
        "--tickers",
        required=True,
        help="Comma-separated ticker symbols, e.g. AAPL,MSFT,TSLA",
    )
    parser.add_argument(
        "--dates",
        required=True,
        help="Comma-separated dates in YYYY-MM-DD format, e.g. 2025-10-31,2025-11-03",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock data instead of live APIs (for quick preview).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers = parse_tickers_input(args.tickers)
    dates = parse_dates_input(args.dates)

    if not tickers:
        raise ValueError("No valid tickers provided. Use --tickers like AAPL,MSFT,TSLA")
    if not dates:
        raise ValueError("No valid dates provided. Use --dates like 2025-10-31,2025-11-03")

    total = len(tickers) * len(dates)
    idx = 0
    for ticker in tickers:
        for date in dates:
            idx += 1
            context = mock_context(ticker, date) if args.mock else fetch_stock_context(ticker, date)
            print(f"[{idx}/{total}] {ticker} on {date}")
            print(explain_move_paragraph(context))
            print()


if __name__ == "__main__":
    main()
