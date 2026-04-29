# KIS API 자동 트레이딩 에이전트 🤖

한국투자증권 KIS API 기반 실시간 국내 + 해외 주식 트레이딩 에이전트

## 파일 구조

```
trading_agent/
├── kis.env              # ✏️  API 키 입력 (필수!)
├── kis_auth.py          # 인증 / 토큰 관리
├── kis_data.py          # 국내·해외 시세 조회
├── kis_order.py         # 주문 실행 / 잔고 조회
├── trading_agent.py     # 메인 트레이딩 에이전트
├── server.py            # 웹 대시보드 서버
├── static/index.html    # 대시보드 UI
├── requirements.txt
└── README.md
```

## 설치 및 실행

```bash
# 1. 패키지 설치
pip install -r requirements.txt

# 2. kis.env 파일 편집 (필수!)
#    KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT, KIS_HTS_ID 입력

# 3. 신호 분석만 (1회)
python trading_agent.py

# 4. 웹 대시보드 실행
python server.py
# → 브라우저에서 http://localhost:5000 접속
```

## kis.env 설정

```
KIS_APP_KEY=발급받은_앱키
KIS_APP_SECRET=발급받은_앱시크릿
KIS_ACCOUNT=계좌번호-01
KIS_HTS_ID=HTS아이디
KIS_VIRTUAL=false        # 모의투자면 true
```

## 자동 주문 활성화

`trading_agent.py` 하단 Config에서:
```python
auto_order=True,       # ⚠️ 실제 주문 발생!
min_strength="강함",   # 강함 신호일 때만 주문
qty_domestic=1,        # 국내 1주씩
qty_overseas=1,        # 해외 1주씩
```

## 지원 종목 예시

| 국내 | 코드 | 해외 | 거래소 |
|------|------|------|--------|
| 삼성전자 | 005930 | AAPL | NASD |
| SK하이닉스 | 000660 | NVDA | NASD |
| NAVER | 035420 | TSLA | NASD |
| 카카오 | 035720 | MSFT | NASD |

## ⚠️ 주의사항

- `auto_order=False` (기본값) 상태에서 신호만 확인 후, 충분히 검증한 뒤 활성화하세요
- KIS API 호출 제한: 초당 20회 (자동 준수됨)
- API 이용기간: 신청일로부터 1년 (갱신 필요)
- 투자 손실에 대한 책임은 본인에게 있습니다
