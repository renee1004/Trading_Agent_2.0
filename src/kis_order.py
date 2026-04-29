"""
kis_order.py — KIS API 주문 실행 모듈
국내/해외 매수·매도·취소 주문을 처리합니다.
⚠️  실전투자 계좌 연결 상태입니다. 신중하게 사용하세요.
"""

import requests
from kis_auth import BASE_URL, ACCOUNT, get_headers, get_access_token
import logging

logger = logging.getLogger(__name__)


# ── 국내주식 주문 ─────────────────────────────────────
def order_domestic(
    symbol: str,
    side: str,          # "BUY" or "SELL"
    qty: int,
    price: int = 0,     # 0 = 시장가
    order_type: str = "01",   # 01=시장가, 00=지정가
) -> dict:
    """
    국내주식 주문 (TTTC0802U: 매수 / TTTC0801U: 매도)
    """
    tr_id = "TTTC0802U" if side == "BUY" else "TTTC0801U"
    token = get_access_token()
    url   = f"{BASE_URL}/uapi/domestic-stock/v1/trading/order-cash"

    acct_no, acct_suffix = ACCOUNT.split("-") if "-" in ACCOUNT else (ACCOUNT, "01")

    body = {
        "CANO":        acct_no,
        "ACNT_PRDT_CD": acct_suffix,
        "PDNO":        symbol,
        "ORD_DVSN":    order_type,
        "ORD_QTY":     str(qty),
        "ORD_UNPR":    str(price),
    }

    headers = get_headers(tr_id, token)
    res = requests.post(url, headers=headers, json=body, timeout=10)
    res.raise_for_status()
    data = res.json()

    if data.get("rt_cd") != "0":
        raise ValueError(f"주문 실패 [{symbol}]: {data.get('msg1')}")

    order_no = data["output"].get("ODNO", "")
    side_kr  = "매수" if side == "BUY" else "매도"
    price_str = "시장가" if price == 0 else f"{price:,}원"
    logger.info(f"✅ 국내 {side_kr} 주문 완료 | {symbol} {qty}주 @ {price_str} | 주문번호: {order_no}")

    return {"order_no": order_no, "symbol": symbol, "side": side,
            "qty": qty, "price": price, "market": "KR"}


# ── 해외주식 주문 ─────────────────────────────────────
def order_overseas(
    symbol: str,
    excd: str,          # "NASD", "NYSE", "AMEX" 등
    side: str,          # "BUY" or "SELL"
    qty: int,
    price: float = 0,   # 0 = 시장가
) -> dict:
    """
    해외주식 주문 (TTTT1002U: 매수 / TTTT1006U: 매도)
    """
    tr_id = "TTTT1002U" if side == "BUY" else "TTTT1006U"
    token = get_access_token()
    url   = f"{BASE_URL}/uapi/overseas-stock/v1/trading/order"

    acct_no, acct_suffix = ACCOUNT.split("-") if "-" in ACCOUNT else (ACCOUNT, "01")
    order_type = "00" if price == 0 else "00"   # 해외는 지정가 권장

    body = {
        "CANO":         acct_no,
        "ACNT_PRDT_CD": acct_suffix,
        "OVRS_EXCG_CD": excd,
        "PDNO":         symbol,
        "ORD_QTY":      str(qty),
        "OVRS_ORD_UNPR": f"{price:.2f}",
        "ORD_SVR_DVSN_CD": "0",
        "ORD_DVSN":     order_type,
    }

    headers = get_headers(tr_id, token)
    res = requests.post(url, headers=headers, json=body, timeout=10)
    res.raise_for_status()
    data = res.json()

    if data.get("rt_cd") != "0":
        raise ValueError(f"해외 주문 실패 [{symbol}]: {data.get('msg1')}")

    order_no = data["output"].get("ODNO", "")
    side_kr  = "매수" if side == "BUY" else "매도"
    logger.info(f"✅ 해외 {side_kr} 주문 완료 | {excd} {symbol} {qty}주 @ ${price:.2f} | 주문번호: {order_no}")

    return {"order_no": order_no, "symbol": symbol, "side": side,
            "qty": qty, "price": price, "excd": excd, "market": "US"}


# ── 잔고 조회 ─────────────────────────────────────────
def get_balance_domestic() -> dict:
    """국내 주식 잔고 조회 (TTTC8434R)"""
    token = get_access_token()
    url   = f"{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance"
    acct_no, acct_suffix = ACCOUNT.split("-") if "-" in ACCOUNT else (ACCOUNT, "01")

    params = {
        "CANO": acct_no, "ACNT_PRDT_CD": acct_suffix,
        "AFHR_FLPR_YN": "N", "OFL_YN": "N", "INQR_DVSN": "02",
        "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "01", "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }
    headers = get_headers("TTTC8434R", token)
    res = requests.get(url, headers=headers, params=params, timeout=10)
    res.raise_for_status()
    data = res.json()

    if data.get("rt_cd") != "0":
        raise ValueError(f"잔고 조회 실패: {data.get('msg1')}")

    output2 = data.get("output2", [{}])[0]
    positions = []
    for item in data.get("output1", []):
        qty = int(item.get("hldg_qty", 0))
        if qty > 0:
            positions.append({
                "symbol":     item.get("pdno"),
                "name":       item.get("prdt_name"),
                "qty":        qty,
                "avg_price":  float(item.get("pchs_avg_pric", 0)),
                "cur_price":  float(item.get("prpr", 0)),
                "profit_pct": float(item.get("evlu_pfls_rt", 0)),
                "profit_amt": float(item.get("evlu_pfls_amt", 0)),
            })

    return {
        "cash":          float(output2.get("dnca_tot_amt", 0)),
        "total_eval":    float(output2.get("tot_evlu_amt", 0)),
        "total_profit":  float(output2.get("evlu_pfls_smtl_amt", 0)),
        "positions":     positions,
    }


def get_balance_overseas() -> dict:
    """해외 주식 잔고 조회 (TTTS3012R)"""
    token = get_access_token()
    url   = f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-balance"
    acct_no, acct_suffix = ACCOUNT.split("-") if "-" in ACCOUNT else (ACCOUNT, "01")

    params = {
        "CANO": acct_no, "ACNT_PRDT_CD": acct_suffix,
        "OVRS_EXCG_CD": "NASD", "TR_CRCY_CD": "USD",
        "CTX_AREA_FK200": "", "CTX_AREA_NK200": "",
    }
    headers = get_headers("TTTS3012R", token)
    res = requests.get(url, headers=headers, params=params, timeout=10)
    res.raise_for_status()
    data = res.json()

    if data.get("rt_cd") != "0":
        raise ValueError(f"해외 잔고 조회 실패: {data.get('msg1')}")

    output2 = data.get("output2", {})
    positions = []
    for item in data.get("output1", []):
        qty = int(item.get("cblc_qty", 0))
        if qty > 0:
            positions.append({
                "symbol":     item.get("ovrs_pdno"),
                "name":       item.get("ovrs_item_name"),
                "qty":        qty,
                "avg_price":  float(item.get("pchs_avg_pric", 0)),
                "cur_price":  float(item.get("now_pric2", 0)),
                "profit_pct": float(item.get("evlu_pfls_rt", 0)),
                "profit_amt": float(item.get("ovrs_stck_evlu_pfls_amt", 0)),
            })

    return {
        "cash_usd":     float(output2.get("frcr_dncl_amt_2", 0)),
        "total_eval":   float(output2.get("tot_evlu_pfls_amt", 0)),
        "positions":    positions,
    }
