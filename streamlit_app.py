import os
from datetime import date, datetime

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(dotenv_path="/Users/fulyayilmaz/Documents/.env")

from app import explain_move_paragraph, fetch_stock_context, parse_tickers_input


SP500_LEADER_SECTORS = {
    "Technology (7)": ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "TSLA", "AMZN"],
    "Finance (4)": ["JPM", "BAC", "V", "GS"],
    "Healthcare (4)": ["JNJ", "UNH", "PFE", "MRNA"],
    "Consumer (4)": ["WMT", "MCD", "NKE", "SBUX"],
    "Energy (2)": ["XOM", "CVX"],
    "Media / Entertainment (2)": ["DIS", "NFLX"],
}

TICKER_COMPANY_NAMES = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "Nvidia", "GOOGL": "Alphabet",
    "META": "Meta", "TSLA": "Tesla", "AMZN": "Amazon", "JPM": "JPMorgan",
    "BAC": "Bank of America", "V": "Visa", "GS": "Goldman Sachs",
    "JNJ": "Johnson & Johnson", "UNH": "UnitedHealth", "PFE": "Pfizer",
    "MRNA": "Moderna", "WMT": "Walmart", "MCD": "McDonald's", "NKE": "Nike",
    "SBUX": "Starbucks", "XOM": "ExxonMobil", "CVX": "Chevron",
    "DIS": "Disney", "NFLX": "Netflix",
}

TERMINAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');

html, body, [class*="css"] {
    background-color: #0a0a0a !important;
    color: #e0e0e0 !important;
    font-family: 'JetBrains Mono', 'Courier New', monospace !important;
}

.stApp { background-color: #0a0a0a !important; }

h1 { color: #ff6b00 !important; letter-spacing: 3px !important; font-size: 2.2rem !important; text-transform: uppercase !important; }
h2, h3 { color: #ff6b00 !important; letter-spacing: 2px !important; text-transform: uppercase !important; }

.stTextArea textarea {
    background-color: #111 !important;
    color: #ccc !important;
    border: 1px solid #2a2a2a !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px !important;
    border-radius: 2px !important;
}

.stSelectbox > div > div {
    background-color: #111 !important;
    border: 1px solid #2a2a2a !important;
    color: #ccc !important;
    border-radius: 2px !important;
}

.stDateInput > div > div > input {
    background-color: #111 !important;
    border: 1px solid #2a2a2a !important;
    color: #ccc !important;
    font-family: 'JetBrains Mono', monospace !important;
    border-radius: 2px !important;
}

.stButton > button {
    background-color: #ff6b00 !important;
    color: #000 !important;
    border: none !important;
    font-weight: bold !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    border-radius: 2px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important;
}

.stButton > button:hover {
    background-color: #e05a00 !important;
}

.stExpander {
    background-color: #111 !important;
    border: 1px solid #1a1a1a !important;
    border-radius: 2px !important;
}

.stMetric {
    background-color: #111 !important;
    border: 1px solid #1a1a1a !important;
    padding: 8px 12px !important;
    border-radius: 2px !important;
}

.stMetric label {
    color: #555 !important;
    font-size: 10px !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
}

.stMetric [data-testid="metric-container"] > div:last-child {
    font-size: 18px !important;
    font-family: 'JetBrains Mono', monospace !important;
}

div[data-testid="stContainer"] {
    background-color: #111 !important;
    border: 1px solid #1a1a1a !important;
    border-radius: 2px !important;
    padding: 16px !important;
}

.stInfo {
    background-color: #111 !important;
    border: 1px solid #2a2a2a !important;
    color: #555 !important;
    border-radius: 2px !important;
}

.stSpinner { color: #ff6b00 !important; }

[data-testid="stSidebar"] {
    background-color: #0d0d0d !important;
    border-right: 1px solid #1a1a1a !important;
}

label, .stMarkdown p {
    color: #aaa !important;
    font-size: 15px !important;
}

.stCaption { color: #555 !important; font-size: 13px !important; }
</style>
"""


def _all_leader_tickers() -> str:
    ordered = []
    for syms in SP500_LEADER_SECTORS.values():
        ordered.extend(syms)
    return ",".join(ordered)


def _build_prompt(context: dict) -> str:
    ticker = context.get("ticker", "UNKNOWN")
    date_str = context.get("date", "")
    price_change = context.get("price_change_pct")
    market_change = context.get("market_change_pct")
    idio = context.get("idiosyncratic_move")
    volume_vs_avg = context.get("volume_vs_avg")
    earnings = context.get("earnings")
    headlines = context.get("headlines") or []
    analyst_rec = context.get("analyst_rec")

    earnings_str = "None detected near this date."
    if earnings:
        earnings_str = (
            f"Period: {earnings.get('period')}, "
            f"Actual EPS: {earnings.get('actual')}, "
            f"Estimate EPS: {earnings.get('estimate')}, "
            f"Surprise: {earnings.get('surprise_pct')}%"
        )

    headlines_str = "No headlines available."
    if headlines:
        items = [h.get("headline", "") for h in headlines[:5] if h.get("headline")]
        headlines_str = "\n".join(f"- {h}" for h in items)

    analyst_str = "No analyst data available."
    if analyst_rec:
        analyst_str = (
            f"Strong Buy: {analyst_rec.get('strongBuy', 0)}, "
            f"Buy: {analyst_rec.get('buy', 0)}, "
            f"Hold: {analyst_rec.get('hold', 0)}, "
            f"Sell: {analyst_rec.get('sell', 0)}, "
            f"Strong Sell: {analyst_rec.get('strongSell', 0)}"
        )

    market_str = f"{market_change:+.2f}%" if market_change is not None else "N/A"
    idio_str = f"{idio:+.2f}%" if idio is not None else "N/A"
    vol_str = f"{volume_vs_avg:.2f}x" if volume_vs_avg is not None else "N/A"
    price_str = f"{price_change:+.2f}%" if price_change is not None else "N/A"

    return f"""You are a financial analyst explaining why a stock moved on a specific date.
Write one concise paragraph followed by two short bullet lists: Micro Drivers and Macro Drivers.
Be direct. Lead with the strongest driver. Do not fabricate facts not in the data.

Ticker: {ticker}
Date: {date_str}
Price Change: {price_str}
Market (SPY) Change: {market_str}
Idiosyncratic Move: {idio_str}
Volume vs 10-day Average: {vol_str}

Earnings (nearby):
{earnings_str}

Top Headlines:
{headlines_str}

Analyst Sentiment:
{analyst_str}

Write the explanation now."""


def call_claude(context: dict) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return "ANTHROPIC_API_KEY is not set. Add it to your .env file."

    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 500,
        "messages": [{"role": "user", "content": _build_prompt(context)}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=body,
            timeout=45,
        )
        if not resp.ok:
            return f"Claude API error ({resp.status_code}): {resp.text}"
        data = resp.json()
        blocks = data.get("content", [])
        text = "\n".join(p.get("text", "") for p in blocks if p.get("type") == "text").strip()
        return text or "Claude returned an empty response."
    except requests.RequestException as e:
        return f"Claude request failed: {e}"


def format_news_lines(headlines: list, max_items: int = 12) -> str:
    lines = []
    for h in (headlines or [])[:max_items]:
        title = h.get("headline") or ""
        if not title:
            continue
        ts = h.get("datetime")
        date_s = ""
        if ts is not None:
            try:
                t = int(ts)
                if t > 1e12:
                    t = int(t / 1000)
                date_s = datetime.utcfromtimestamp(t).strftime("%Y-%m-%d")
            except (TypeError, ValueError, OSError):
                pass
        src = (h.get("source") or "").strip()
        bit = f"**{date_s}** " if date_s else ""
        bit += f"[{src}] " if src else ""
        bit += title
        lines.append(f"- {bit}")
    return "\n".join(lines) if lines else "_No headlines found._"


# ── Page setup ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="StockMove", page_icon="📉", layout="wide")
st.markdown(TERMINAL_CSS, unsafe_allow_html=True)

st.title("STOCKMOVE")
st.markdown("Identify top stock movers and get AI-powered explanations of the market, sector, and company factors behind them.")
st.caption("Select a date · Filter by move · Click AI EXPLANATION for a Claude-powered breakdown")

if "tickers_text" not in st.session_state:
    st.session_state["tickers_text"] = _all_leader_tickers()
if "ai_explanations" not in st.session_state:
    st.session_state["ai_explanations"] = {}

with st.sidebar:
    st.markdown("### UNIVERSE")
    st.caption("S&P-style large-cap presets")
    if st.button("ALL 23 LEADERS"):
        st.session_state["tickers_text"] = _all_leader_tickers()
    for idx, (sector_name, syms) in enumerate(SP500_LEADER_SECTORS.items()):
        short = sector_name.split(" (")[0].upper()
        if st.button(short, key=f"preset_btn_{idx}"):
            st.session_state["tickers_text"] = ",".join(syms)
    st.divider()

tickers_text = st.text_area(
    "TICKERS",
    key="tickers_text",
    help="Comma-separated. Use sidebar presets or type your own.",
    height=80,
).strip()

col1, col2, col3 = st.columns([2, 2, 1])
with col1:
    target_date = st.date_input("DATE", value=date.today())
with col2:
    move_filter = st.selectbox(
        "FILTER",
        options=["Declines only", "Peaks only", "Both"],
        index=0,
    )
with col3:
    st.markdown("<br>", unsafe_allow_html=True)
    generate = st.button("GENERATE", type="primary", use_container_width=True)

if generate:
    st.session_state["ai_explanations"] = {}
    tickers = parse_tickers_input(tickers_text)
    if not tickers:
        st.error("Please enter at least one ticker.")
        st.stop()

    date_str = target_date.strftime("%Y-%m-%d")
    results = []

    with st.spinner("FETCHING MARKET DATA..."):
        for ticker in tickers:
            try:
                context = fetch_stock_context(ticker, date_str)
                move = context.get("price_change_pct")
                is_down = move is not None and move < 0
                is_up = move is not None and move > 0
                include = (
                    (move_filter == "Declines only" and is_down)
                    or (move_filter == "Peaks only" and is_up)
                    or (move_filter == "Both" and move is not None)
                )
                if not include:
                    continue
                results.append({
                    "ticker": ticker,
                    "move": move,
                    "context": context,
                })
            except Exception as exc:
                results.append({
                    "ticker": ticker,
                    "move": None,
                    "context": {},
                    "error": str(exc),
                })

    st.session_state["results"] = results
    st.session_state["ran"] = True

# ── Results ───────────────────────────────────────────────────────────────────
if st.session_state.get("ran") and st.session_state.get("results"):
    results = st.session_state["results"]
    results.sort(key=lambda r: (r["move"] is None, r["move"] if r["move"] is not None else 999))

    st.markdown(f"### RESULTS — {len(results)} STOCKS")
    st.divider()

    for item in results:
        ticker = item["ticker"]
        move = item["move"]
        name = TICKER_COMPANY_NAMES.get(ticker, "")
        ctx = item.get("context") or {}

        # Color the move
        if move is not None:
            color = "#ff3b3b" if move < 0 else "#00cc66"
            move_str = f"{move:+.2f}%"
        else:
            color = "#555"
            move_str = "N/A"

        with st.container(border=True):
            # Header row
            st.markdown(
                f"<div style='display:flex;align-items:center;justify-content:space-between;margin-bottom:12px'>"
                f"<span style='font-size:18px;font-weight:bold;color:#fff;letter-spacing:2px'>{ticker}"
                f"<span style='font-size:12px;color:#555;margin-left:10px;font-weight:normal'>{name}</span></span>"
                f"<span style='font-size:20px;font-weight:bold;color:{color};font-family:monospace'>{move_str}</span>"
                f"</div>",
                unsafe_allow_html=True
            )

            # Metrics
            m1, m2, m3 = st.columns(3)
            spy = ctx.get("market_change_pct")
            idio = ctx.get("idiosyncratic_move")
            vol = ctx.get("volume_vs_avg")
            with m1:
                st.metric("SPY", f"{spy:+.2f}%" if spy is not None else "N/A")
            with m2:
                st.metric("VS MARKET", f"{idio:+.2f}%" if idio is not None else "N/A")
            with m3:
                st.metric("VOLUME", f"{vol:.2f}x avg" if vol is not None else "N/A")

            # Headlines
            with st.expander("HEADLINES & NEWS", expanded=False):
                st.markdown(format_news_lines(ctx.get("headlines")))

            # AI explanation
            ai_key = f"{ticker}_{ctx.get('date', '')}"
            if ai_key in st.session_state["ai_explanations"]:
                st.markdown(
                    "<div style='border-left:2px solid #ff6b00;padding:10px 14px;margin-top:12px;"
                    "background:#0d0d0d;font-size:15px;line-height:1.8;color:#aaa'>"
                    "<div style='color:#ff6b00;font-size:15px;letter-spacing:2px;text-transform:uppercase;"
                    "margin-bottom:11px'>AI EXPLANATION (CLAUDE)</div>"
                    + st.session_state["ai_explanations"][ai_key].replace("\n", "<br>").replace("**", "<b>").replace("</b><b>", "") +
                    "</div>",
                    unsafe_allow_html=True
                )
            else:
                if st.button(f"AI EXPLANATION — {ticker}", key=f"ai_btn_{ticker}"):
                    with st.spinner(f"ANALYZING {ticker} WITH CLAUDE..."):
                        explanation = call_claude(item["context"])
                        st.session_state["ai_explanations"][ai_key] = explanation
                    st.rerun()

            with st.expander("RAW DATA", expanded=False):
                st.json(item["context"])