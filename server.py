"""
server.py — KIS API 기반 트레이딩 대시보드 서버
실행: python server.py
브라우저: http://localhost:5000
"""

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import os, json
from datetime import datetime
import numpy as np
import pandas as pd

from kis_auth import check_config, get_access_token
from kis_data import get_price, get_ohlcv, OVERSEAS_EXCD_MAP
from kis_order import get_balance_domestic, get_balance_overseas

app = Flask(__name__, static_folder="static")
CORS(app)

SYMBOLS = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "035420": "NAVER",
    "035720": "카카오",
    "005380": "현대차",
    "AAPL":   "애플",
    "NVDA":   "엔비디아",
    "TSLA":   "테슬라",
    "MSFT":   "마이크로소프트",
    "AMZN":   "아마존",
}


def calc_indicators(close: pd.Series):
    ma5  = float(close.rolling(5).mean().iloc[-1])
    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma60 = float(close.rolling(60).mean().iloc[-1])

    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rsi   = float((100 - 100 / (1 + gain / loss.replace(0, np.nan))).iloc[-1])

    e12  = close.ewm(span=12, adjust=False).mean()
    e26  = close.ewm(span=26, adjust=False).mean()
    macd_line = e12 - e26
    sig_line  = macd_line.ewm(span=9, adjust=False).mean()
    macd = float(macd_line.iloc[-1])
    sig  = float(sig_line.iloc[-1])

    return ma5, ma20, ma60, rsi, macd, sig


def get_signal(ma5, ma20, rsi, macd, sig):
    buy = sell = 0; rsns = []
    if ma5 > ma20: buy += 1;  rsns.append("MA골든크로스")
    else:          sell += 1; rsns.append("MA데드크로스")
    if rsi < 30:   buy += 2;  rsns.append(f"RSI과매도({rsi:.0f})")
    elif rsi > 70: sell += 2; rsns.append(f"RSI과매수({rsi:.0f})")
    if macd > sig: buy += 1;  rsns.append("MACD상승")
    else:          sell += 1; rsns.append("MACD하락")
    r = " · ".join(rsns)
    if buy > sell:  return "BUY",  "강함" if buy >= 3 else "보통",  r
    if sell > buy:  return "SELL", "강함" if sell >= 3 else "보통", r
    return "HOLD", "약함", r


@app.route("/api/analyze/<symbol>")
def analyze(symbol):
    try:
        info = get_price(symbol)
        df   = get_ohlcv(symbol, count=100)
        if df.empty or len(df) < 60:
            return jsonify({"error": "데이터 부족"}), 400

        close = df["Close"].squeeze()
        ma5, ma20, ma60, rsi, macd_val, sig_val = calc_indicators(close)
        action, strength, reason = get_signal(ma5, ma20, rsi, macd_val, sig_val)

        is_kr  = info["market"] == "KR"
        fmt    = lambda v: f"{v:,.0f}원" if is_kr else f"${v:.2f}"
        chart_dates  = [str(d.date()) for d in df["Date"].iloc[-60:]]
        chart_prices = [round(float(p), 2) for p in close.iloc[-60:]]
        chart_ma20   = [round(float(v), 2) if not np.isnan(v) else None
                        for v in close.rolling(20).mean().iloc[-60:]]

        return jsonify({
            "symbol":    symbol,
            "name":      info.get("name", SYMBOLS.get(symbol, symbol)),
            "market":    info["market"],
            "price":     info["price"],
            "price_fmt": fmt(info["price"]),
            "change":    info.get("change", 0),
            "ma5_fmt":   fmt(ma5),  "ma20_fmt": fmt(ma20), "ma60_fmt": fmt(ma60),
            "ma5": ma5, "ma20": ma20,
            "rsi":       round(rsi, 1),
            "macd":      round(macd_val, 4),
            "macd_sig":  round(sig_val, 4),
            "action":    action,
            "strength":  strength,
            "reason":    reason,
            "chart":     {"dates": chart_dates, "prices": chart_prices, "ma20": chart_ma20},
            "updated":   datetime.now().strftime("%H:%M:%S"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/balance")
def balance():
    result = {}
    try:
        result["domestic"] = get_balance_domestic()
    except Exception as e:
        result["domestic"] = {"error": str(e)}
    try:
        result["overseas"] = get_balance_overseas()
    except Exception as e:
        result["overseas"] = {"error": str(e)}
    return jsonify(result)


@app.route("/api/symbols")
def symbols():
    return jsonify(SYMBOLS)


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


if __name__ == "__main__":
    check_config()
    print("=" * 55)
    print("🚀 KIS 트레이딩 대시보드 서버 시작!")
    print("   브라우저: http://localhost:5000")
    print("   종료:     Ctrl+C")
    print("=" * 55)
    app.run(debug=False, port=5000)
