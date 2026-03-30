# Stock Move Explainer

This project explains why a stock moved on a specific date, using:
- price and volume data from Yahoo Finance (`yfinance`)
- news, earnings, and analyst data from Finnhub

## Files

- `app.py` - CLI app
- `requirements.txt` - Python dependencies

## 1) Install Python tools (macOS only, if needed)

If `python`/`git` commands fail with `xcode-select` errors, run:

```bash
xcode-select --install
```

Then restart Terminal.

## 2) Create and activate a virtual environment

From this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3) Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 4) Run the app

### Quick preview without API keys

```bash
python app.py --tickers AAPL,MSFT,TSLA --dates 2025-10-31,2025-11-03 --mock
```

### Live data mode

Set your Finnhub key:

```bash
export FINNHUB_KEY="your_real_finnhub_key"
```

Then run:

```bash
python app.py --tickers AAPL,MSFT,TSLA --dates 2025-10-31,2025-11-03
```

## Visual app (browser UI)

The Streamlit app supports:
- many tickers at once, with **sidebar presets** for 23 large-cap sector leaders (Tech, Finance, Healthcare, Consumer, Energy, Media)
- **headline news** around the selected date (Finnhub when `FINNHUB_KEY` is set, plus Yahoo Finance ticker news)
- move filter: declines only, peaks (up) only, or both
- optional **Claude** micro + macro explanations (`ANTHROPIC_API_KEY`)

Install dependencies:

```bash
pip install -r requirements.txt
```

Run:

```bash
streamlit run streamlit_app.py
```

Then open the local URL shown in terminal (usually `http://localhost:8501`).

For Claude explanations, set your API key before launching Streamlit:

```bash
export ANTHROPIC_API_KEY="your_real_anthropic_key"
```

## Notes

- `--dates` accepts one or many comma-separated dates in `YYYY-MM-DD` format.
- `--tickers` accepts one or many comma-separated symbols.
- If the market was closed on that date, the app may say no valid trading data was found.
- International suffix examples: London `.L` (`HSBA.L`), Tokyo `.T` (`7203.T`), Paris `.PA` (`AIR.PA`).
