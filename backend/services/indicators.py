"""Technical indicator computation from OHLCV DataFrames (no API calls, pandas_ta)."""
from __future__ import annotations

import pandas as pd

from backend.services.types import TechnicalSnapshot


def compute_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return df.ta.rsi(length=period)


def compute_macd(df: pd.DataFrame) -> pd.DataFrame:
    return df.ta.macd()


def compute_bbands(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    return df.ta.bbands(length=period)


def compute_sma(df: pd.DataFrame, periods: list[int] | None = None) -> pd.DataFrame:
    if periods is None:
        periods = [50, 200]
    result = pd.DataFrame(index=df.index)
    for p in periods:
        result[f"SMA_{p}"] = df.ta.sma(length=p)
    return result


def technical_summary(df: pd.DataFrame) -> tuple[TechnicalSnapshot, dict]:
    """Compute a TechnicalSnapshot from an OHLCV DataFrame."""
    if df.empty or len(df) < 20:
        return TechnicalSnapshot()

    close = df["Close"]
    latest = float(close.iloc[-1])

    # RSI
    rsi_series = compute_rsi(df)
    rsi = float(rsi_series.iloc[-1]) if rsi_series is not None and not rsi_series.empty else None

    # MACD
    macd_df = compute_macd(df)
    macd_signal = "neutral"
    if macd_df is not None and not macd_df.empty:
        cols = macd_df.columns.tolist()
        macd_col = next((c for c in cols if c.startswith("MACD_") and "h" not in c and "s" not in c.lower()), None)
        signal_col = next((c for c in cols if "MACDs" in c), None)
        if macd_col and signal_col:
            m = float(macd_df[macd_col].iloc[-1])
            s = float(macd_df[signal_col].iloc[-1])
            m_prev = float(macd_df[macd_col].iloc[-2]) if len(macd_df) > 1 else m
            s_prev = float(macd_df[signal_col].iloc[-2]) if len(macd_df) > 1 else s
            if m > s and m_prev <= s_prev:
                macd_signal = "bullish_cross"
            elif m < s and m_prev >= s_prev:
                macd_signal = "bearish_cross"
            elif m > s:
                macd_signal = "bullish"
            elif m < s:
                macd_signal = "bearish"

    # SMAs
    sma_df = compute_sma(df)
    price_vs_sma50 = "above"
    price_vs_sma200 = "above"
    if "SMA_50" in sma_df.columns:
        s50 = sma_df["SMA_50"].dropna()
        if not s50.empty:
            price_vs_sma50 = "above" if latest > float(s50.iloc[-1]) else "below"
    if "SMA_200" in sma_df.columns:
        s200 = sma_df["SMA_200"].dropna()
        if not s200.empty:
            price_vs_sma200 = "above" if latest > float(s200.iloc[-1]) else "below"

    # Bollinger Bands
    bb_df = compute_bbands(df)
    bollinger_position = "middle"
    if bb_df is not None and not bb_df.empty:
        upper_col = next((c for c in bb_df.columns if "BBU" in c), None)
        lower_col = next((c for c in bb_df.columns if "BBL" in c), None)
        if upper_col and lower_col:
            upper = float(bb_df[upper_col].iloc[-1])
            lower = float(bb_df[lower_col].iloc[-1])
            if latest >= upper:
                bollinger_position = "upper"
            elif latest <= lower:
                bollinger_position = "lower"

    # Trend: compare current close to SMA50 direction over last 20 bars
    trend = "sideways"
    if "SMA_50" in sma_df.columns:
        s50 = sma_df["SMA_50"].dropna()
        if len(s50) >= 20:
            slope = float(s50.iloc[-1]) - float(s50.iloc[-20])
            if slope > 0 and price_vs_sma50 == "above":
                trend = "up"
            elif slope < 0 and price_vs_sma50 == "below":
                trend = "down"

    # Momentum from RSI
    momentum = "weak"
    if rsi is not None:
        if rsi > 60:
            momentum = "strong"
        elif rsi < 40:
            momentum = "diverging"

    key_levels: dict = {}
    if len(close) >= 20:
        key_levels["support_20d"] = round(float(close.iloc[-20:].min()), 2)
        key_levels["resistance_20d"] = round(float(close.iloc[-20:].max()), 2)

    return TechnicalSnapshot(
        rsi=round(rsi, 2) if rsi is not None else None,
        macd_signal=macd_signal,
        price_vs_sma50=price_vs_sma50,
        price_vs_sma200=price_vs_sma200,
        bollinger_position=bollinger_position,
        trend=trend,
        momentum=momentum,
    ), key_levels


def full_technical(df: pd.DataFrame) -> tuple[TechnicalSnapshot, dict]:
    """Returns (snapshot, key_levels). Handles the tuple return from technical_summary."""
    result = technical_summary(df)
    if isinstance(result, tuple):
        return result
    return result, {}
