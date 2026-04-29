"""
kis_data.py — KIS API 시세 조회 모듈
국내주식 / 해외주식 현재가 및 일봉 데이터를 가져옵니다.
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from kis_auth import BASE_URL, ACCOUNT, get_headers, get_access_token
import logging

logger = logging.getLogger(__name__)

# 해외 거래소 코드
EXCD = {
    "NASD": "NASDAQ",
    "NYSE": "NYSE",
    "AMEX": "AMEX",
    "TKSE": "도쿄",
    "SEHK": "홍콩",
}

# 종목 → 거래소 자동 매핑 (확장 가능)
OVERSEAS_EXCD_MAP = {
    "AAPL": "NASD", "NVDA": "NASD", "TSLA": "NASD",
    "MSFT": "NASD", "GOOGL": "NASD", "AMZN": "NASD",
    "META": "NASD", "NFLX": "NASD",
    "JPM":  "NYSE", "BAC": "NYSE", "GS": "NYSE",
}


# ── 국내주식 ──────────────────────────────────────────
def get_domestic_price(symbol: str) -> dict:
    """국내주식 현재가 조회 (FHKST01010100)"""
    token = get_access_token()
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = get_headers("FHKST01010100", token)
    params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": symbol}

    res = requests.get(url, headers=headers, params=params, timeout=10)
    res.raise_for_status()
    data = res.json()

    if data.get("rt_cd") != "0":
        raise ValueError(f"[{symbol}] 국내 시세 조회 실패: {data.get('msg1')}")

    o = data["output"]
    return {
        "symbol":   symbol,
        "name":     o.get("hts_kor_isnm", symbol),
        "price":    float(o.get("stck_prpr", 0)),
        "open":     float(o.get("stck_oprc", 0)),
        "high":     float(o.get("stck_hgpr", 0)),
        "low":      float(o.get("stck_lwpr", 0)),
        "volume":   int(o.get("acml_vol", 0)),
        "change":   float(o.get("prdy_ctrt", 0)),       # 전일 대비율
        "change_val": float(o.get("prdy_vrss", 0)),     # 전일 대비
        "market":   "KR",
        "currency": "KRW",
    }


def get_domestic_ohlcv(symbol: str, count: int = 100) -> pd.DataFrame:
    """국내주식 일봉 조회 (FHKST01010400)"""
    token = get_access_token()
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-price"
    headers = get_headers("FHKST01010400", token)
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": symbol,
        "fid_org_adj_prc": "1",         # 수정주가
        "fid_period_div_code": "D",     # 일봉
    }

    res = requests.get(url, headers=headers, params=params, timeout=10)
    res.raise_for_status()
    data = res.json()

    if data.get("rt_cd") != "0":
        raise ValueError(f"[{symbol}] 국내 일봉 조회 실패: {data.get('msg1')}")

    rows = data.get("output2", [])
    if not rows:
        raise ValueError(f"[{symbol}] 일봉 데이터 없음")

    df = pd.DataFrame(rows)
    df = df.rename(columns={
        "stck_bsop_date": "Date",
        "stck_oprc": "Open",
        "stck_hgpr": "High",
        "stck_lwpr": "Low",
        "stck_clpr": "Close",
        "acml_vol":  "Volume",
    })
    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    df["Date"]   = pd.to_datetime(df["Date"])
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("Date").reset_index(drop=True)
    return df.tail(count)


# ── 해외주식 ──────────────────────────────────────────
def get_overseas_price(symbol: str, excd: str = None) -> dict:
    """해외주식 현재가 조회 (HHDFS00000300)"""
    if excd is None:
        excd = OVERSEAS_EXCD_MAP.get(symbol.upper(), "NASD")

    token = get_access_token()
    url = f"{BASE_URL}/uapi/overseas-price/v1/quotations/price"
    headers = get_headers("HHDFS00000300", token)
    params = {"AUTH": "", "EXCD": excd, "SYMB": symbol}

    res = requests.get(url, headers=headers, params=params, timeout=10)
    res.raise_for_status()
    data = res.json()

    if data.get("rt_cd") != "0":
        raise ValueError(f"[{symbol}] 해외 시세 조회 실패: {data.get('msg1')}")

    o = data["output"]
    price = float(o.get("last", 0))
    prev  = float(o.get("base", price))
    change_pct = ((price - prev) / prev * 100) if prev else 0

    return {
        "symbol":   symbol,
        "name":     o.get("name", symbol),
        "price":    price,
        "open":     float(o.get("open", 0)),
        "high":     float(o.get("high", 0)),
        "low":      float(o.get("low", 0)),
        "volume":   int(o.get("tvol", 0)),
        "change":   round(change_pct, 2),
        "change_val": round(price - prev, 2),
        "market":   "US",
        "currency": "USD",
        "excd":     excd,
    }


def get_overseas_ohlcv(symbol: str, excd: str = None, count: int = 100) -> pd.DataFrame:
    """해외주식 일봉 조회 (HHDFS76240000)"""
    if excd is None:
        excd = OVERSEAS_EXCD_MAP.get(symbol.upper(), "NASD")

    token = get_access_token()
    url = f"{BASE_URL}/uapi/overseas-price/v1/quotations/dailyprice"
    headers = get_headers("HHDFS76240000", token)

    end_date   = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=200)).strftime("%Y%m%d")

    params = {
        "AUTH":      "",
        "EXCD":      excd,
        "SYMB":      symbol,
        "GUBN":      "0",           # 0: 일봉
        "BYMD":      end_date,
        "MODP":      "1",           # 수정주가
        "KEYB":      "",
    }

    res = requests.get(url, headers=headers, params=params, timeout=10)
    res.raise_for_status()
    data = res.json()

    if data.get("rt_cd") != "0":
        raise ValueError(f"[{symbol}] 해외 일봉 조회 실패: {data.get('msg1')}")

    rows = data.get("output2", [])
    if not rows:
        raise ValueError(f"[{symbol}] 해외 일봉 데이터 없음")

    df = pd.DataFrame(rows)
    df = df.rename(columns={
        "xymd": "Date", "open": "Open",
        "high": "High", "low":  "Low",
        "clos": "Close", "tvol": "Volume",
    })
    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    df["Date"] = pd.to_datetime(df["Date"])
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("Date").reset_index(drop=True)
    return df.tail(count)


# ── 편의 함수 ─────────────────────────────────────────
def get_price(symbol: str) -> dict:
    """국내/해외 자동 판별 후 현재가 반환"""
    if symbol.upper() in OVERSEAS_EXCD_MAP or len(symbol) <= 5 and symbol.isalpha():
        return get_overseas_price(symbol)
    else:
        return get_domestic_price(symbol)


def get_ohlcv(symbol: str, count: int = 100) -> pd.DataFrame:
    """국내/해외 자동 판별 후 일봉 반환"""
    if symbol.upper() in OVERSEAS_EXCD_MAP or len(symbol) <= 5 and symbol.isalpha():
        return get_overseas_ohlcv(symbol, count=count)
    else:
        return get_domestic_ohlcv(symbol, count=count)
