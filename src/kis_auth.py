"""
kis_auth.py — KIS API 인증 모듈
접근토큰 발급 및 자동 갱신을 담당합니다.
"""

import os, json, time, requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv("kis.env")

# ── 설정 ──────────────────────────────────────────────
APP_KEY    = os.getenv("KIS_APP_KEY", "")
APP_SECRET = os.getenv("KIS_APP_SECRET", "")
ACCOUNT    = os.getenv("KIS_ACCOUNT", "")
HTS_ID     = os.getenv("KIS_HTS_ID", "")
IS_VIRTUAL = os.getenv("KIS_VIRTUAL", "false").lower() == "true"

# 실전 / 모의 도메인
BASE_URL = "https://openapivts.koreainvestment.com:29443" if IS_VIRTUAL \
           else "https://openapi.koreainvestment.com:9443"

TOKEN_CACHE = Path("kis_token.json")


def _load_cached_token() -> dict | None:
    """캐시된 토큰 로드 (유효시간 내면 재사용)"""
    if not TOKEN_CACHE.exists():
        return None
    try:
        data = json.loads(TOKEN_CACHE.read_text(encoding="utf-8"))
        expires_at = datetime.fromisoformat(data["expires_at"])
        if datetime.now() < expires_at - timedelta(minutes=10):
            return data
    except Exception:
        pass
    return None


def get_access_token() -> str:
    """접근토큰 반환 (캐시 → 신규발급)"""
    cached = _load_cached_token()
    if cached:
        return cached["access_token"]

    url = f"{BASE_URL}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
    }
    res = requests.post(url, json=body, timeout=10)
    res.raise_for_status()
    data = res.json()

    token = data["access_token"]
    expires_in = int(data.get("expires_in", 86400))
    expires_at = datetime.now() + timedelta(seconds=expires_in)

    TOKEN_CACHE.write_text(json.dumps({
        "access_token": token,
        "expires_at": expires_at.isoformat(),
    }, ensure_ascii=False), encoding="utf-8")

    print(f"✅ KIS 토큰 발급 완료 (만료: {expires_at.strftime('%Y-%m-%d %H:%M')})")
    return token


def get_headers(tr_id: str, token: str = None) -> dict:
    """공통 요청 헤더 생성"""
    if token is None:
        token = get_access_token()
    return {
        "content-type":  "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey":        APP_KEY,
        "appsecret":     APP_SECRET,
        "tr_id":         tr_id,
        "custtype":      "P",
    }


def check_config():
    """설정 검증"""
    missing = []
    if not APP_KEY:    missing.append("KIS_APP_KEY")
    if not APP_SECRET: missing.append("KIS_APP_SECRET")
    if not ACCOUNT:    missing.append("KIS_ACCOUNT")
    if missing:
        raise ValueError(f"kis.env 파일에 다음 값을 입력하세요: {', '.join(missing)}")
    mode = "모의투자" if IS_VIRTUAL else "실전투자"
    print(f"🔑 KIS API 설정 확인 완료 [{mode}] 계좌: {ACCOUNT}")
