"""
trading_agent.py — KIS API 기반 자동 트레이딩 에이전트
국내 + 해외 주식 실시간 데이터로 매매 신호를 생성하고 자동 주문합니다.
"""

import time, json, logging
from datetime import datetime
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from kis_auth import check_config
from kis_data import get_price, get_ohlcv, OVERSEAS_EXCD_MAP
from kis_order import order_domestic, order_overseas, get_balance_domestic, get_balance_overseas

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("trading_agent.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


@dataclass
class Config:
    symbols: list = None
    interval_seconds: int = 60
    ma_short: int = 5
    ma_mid:   int = 20
    ma_long:  int = 60
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold:   float = 30.0
    strategy: str = "combo"
    auto_order: bool = False        # ⚠️ True = 실제 주문 발생
    qty_domestic:  int = 1
    qty_overseas:  int = 1
    min_strength:  str = "강함"

    def __post_init__(self):
        if self.symbols is None:
            self.symbols = ["005930","000660","035420","AAPL","NVDA","TSLA"]


@dataclass
class Signal:
    symbol: str; market: str; action: str; price: float
    rsi: float; ma5: float; ma20: float
    macd: float; macd_sig: float
    strength: str; reason: str; timestamp: str


class Indicators:
    @staticmethod
    def sma(s, p): return float(s.rolling(p).mean().iloc[-1])
    @staticmethod
    def rsi(s, p=14):
        d = s.diff()
        g = d.clip(lower=0).rolling(p).mean()
        l = (-d.clip(upper=0)).rolling(p).mean()
        return float((100 - 100 / (1 + g / l.replace(0, np.nan))).iloc[-1])
    @staticmethod
    def macd(s):
        e12 = s.ewm(span=12, adjust=False).mean()
        e26 = s.ewm(span=26, adjust=False).mean()
        line = e12 - e26
        sig = line.ewm(span=9, adjust=False).mean()
        return float(line.iloc[-1]), float(sig.iloc[-1])


class Strategy:
    STRENGTH_RANK = {"약함": 0, "보통": 1, "강함": 2}

    def __init__(self, cfg):
        self.cfg = cfg
        self.ind = Indicators()

    def analyze(self, df, info):
        close = df["Close"].squeeze()
        ma5  = self.ind.sma(close, self.cfg.ma_short)
        ma20 = self.ind.sma(close, self.cfg.ma_mid)
        rsi  = self.ind.rsi(close, self.cfg.rsi_period)
        macd_val, sig_val = self.ind.macd(close)

        s = self.cfg.strategy
        if s == "ma":      action, strength, reason = self._ma(ma5, ma20)
        elif s == "rsi":   action, strength, reason = self._rsi(rsi)
        elif s == "macd":  action, strength, reason = self._macd(macd_val, sig_val)
        else:              action, strength, reason = self._combo(ma5, ma20, rsi, macd_val, sig_val)

        return Signal(
            symbol=info["symbol"], market=info["market"], action=action, price=info["price"],
            rsi=round(rsi,1), ma5=round(ma5,2), ma20=round(ma20,2),
            macd=round(macd_val,4), macd_sig=round(sig_val,4),
            strength=strength, reason=reason,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _ma(self, ma5, ma20):
        if ma5 > ma20: return "BUY", "보통", "MA5>MA20 골든크로스"
        return "SELL", "보통", "MA5<MA20 데드크로스"

    def _rsi(self, rsi):
        if rsi < self.cfg.rsi_oversold:  return "BUY",  "강함", f"RSI {rsi:.1f} 과매도"
        if rsi > self.cfg.rsi_overbought: return "SELL", "강함", f"RSI {rsi:.1f} 과매수"
        return "HOLD", "약함", f"RSI {rsi:.1f} 중립"

    def _macd(self, macd, sig):
        if macd > sig: return "BUY",  "보통", "MACD 골든크로스"
        return "SELL", "보통", "MACD 데드크로스"

    def _combo(self, ma5, ma20, rsi, macd, sig):
        buy = sell = 0; rsns = []
        if ma5 > ma20: buy += 1; rsns.append("MA골든")
        else: sell += 1; rsns.append("MA데드")
        if rsi < self.cfg.rsi_oversold:   buy += 2;  rsns.append(f"RSI과매도({rsi:.0f})")
        elif rsi > self.cfg.rsi_overbought: sell += 2; rsns.append(f"RSI과매수({rsi:.0f})")
        if macd > sig: buy += 1; rsns.append("MACD↑")
        else: sell += 1; rsns.append("MACD↓")
        r = " · ".join(rsns)
        if buy > sell:  return "BUY",  "강함" if buy >= 3 else "보통",  f"복합매수 [{r}]"
        if sell > buy:  return "SELL", "강함" if sell >= 3 else "보통", f"복합매도 [{r}]"
        return "HOLD", "약함", f"중립 [{r}]"

    def meets_min_strength(self, s):
        return self.STRENGTH_RANK.get(s,0) >= self.STRENGTH_RANK.get(self.cfg.min_strength,1)


def execute_order(signal, cfg):
    if signal.action == "HOLD": return
    if not Strategy(cfg).meets_min_strength(signal.strength):
        logger.info(f"⏭  [{signal.symbol}] 강도 부족({signal.strength}) 주문 건너뜀"); return
    try:
        if signal.market == "KR":
            order_domestic(symbol=signal.symbol, side=signal.action, qty=cfg.qty_domestic, price=0)
        else:
            excd = OVERSEAS_EXCD_MAP.get(signal.symbol.upper(), "NASD")
            order_overseas(symbol=signal.symbol, excd=excd, side=signal.action,
                           qty=cfg.qty_overseas, price=round(signal.price, 2))
    except Exception as e:
        logger.error(f"❌ 주문 실패 [{signal.symbol}]: {e}")


class TradingAgent:
    def __init__(self, cfg):
        self.cfg = cfg
        self.strategy = Strategy(cfg)

    def run_once(self):
        logger.info(f"\n{'─'*55}\n🤖 KIS 분석 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
        signals = []
        for sym in self.cfg.symbols:
            try:
                info = get_price(sym)
                df   = get_ohlcv(sym, count=100)
                if len(df) < self.cfg.ma_long:
                    logger.warning(f"[{sym}] 일봉 부족 ({len(df)}개)"); continue
                signal = self.strategy.analyze(df, info)
                signals.append(signal)
                mkt = "🇰🇷" if signal.market == "KR" else "🇺🇸"
                emoji = {"BUY":"🟢","SELL":"🔴","HOLD":"⚪"}.get(signal.action,"⚪")
                ps = f"{signal.price:,.0f}원" if signal.market == "KR" else f"${signal.price:.2f}"
                logger.info(f"{mkt}{emoji} [{sym}] {signal.action}({signal.strength}) | {ps} | RSI {signal.rsi} | {signal.reason}")
                if self.cfg.auto_order:
                    execute_order(signal, self.cfg)
            except Exception as e:
                logger.error(f"[{sym}] 오류: {e}")
        self._save(signals)
        self._print_balance()
        return signals

    def run_loop(self):
        logger.info(f"🚀 KIS 에이전트 시작 | 전략:{self.cfg.strategy} | 자동주문:{self.cfg.auto_order}")
        try:
            while True:
                self.run_once()
                logger.info(f"⏳ {self.cfg.interval_seconds}초 후 재분석...")
                time.sleep(self.cfg.interval_seconds)
        except KeyboardInterrupt:
            logger.info("⛔ 종료")

    def _save(self, signals):
        if not signals: return
        try:
            try:
                with open("signals.json","r",encoding="utf-8") as f: history = json.load(f)
            except: history = []
            history.extend([asdict(s) for s in signals])
            with open("signals.json","w",encoding="utf-8") as f:
                json.dump(history[-1000:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"저장 실패: {e}")

    def _print_balance(self):
        try:
            kr = get_balance_domestic()
            print(f"\n{'='*55}")
            print(f"🇰🇷 국내 | 현금: {kr['cash']:,.0f}원 | 평가: {kr['total_eval']:,.0f}원 | 손익: {kr['total_profit']:+,.0f}원")
            for p in kr["positions"]:
                e = "🟢" if p['profit_pct'] >= 0 else "🔴"
                print(f"  {e} {p['name']} {p['qty']}주 | 평균 {p['avg_price']:,.0f}원 | {p['profit_pct']:+.2f}%")
        except Exception as e:
            logger.debug(f"국내 잔고 실패: {e}")
        try:
            us = get_balance_overseas()
            print(f"🇺🇸 해외 | USD: ${us['cash_usd']:,.2f}")
            for p in us["positions"]:
                e = "🟢" if p['profit_pct'] >= 0 else "🔴"
                print(f"  {e} {p['name']} {p['qty']}주 | 평균 ${p['avg_price']:.2f} | {p['profit_pct']:+.2f}%")
            print("="*55)
        except Exception as e:
            logger.debug(f"해외 잔고 실패: {e}")


if __name__ == "__main__":
    check_config()

    cfg = Config(
        symbols=["005930","000660","035420","AAPL","NVDA","TSLA"],
        strategy="combo",
        interval_seconds=60,
        auto_order=False,       # ⚠️ True로 바꾸면 실제 주문 발생!
        qty_domestic=1,
        qty_overseas=1,
        min_strength="강함",
    )
    agent = TradingAgent(cfg)
    agent.run_once()
    # agent.run_loop()  # 반복 실행 시 주석 해제
