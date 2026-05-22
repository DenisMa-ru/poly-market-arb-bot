from __future__ import annotations

from src.strategy.ws_signal import WsSignalConfig, WsSignalRunner


def _config() -> WsSignalConfig:
    return WsSignalConfig(
        runtime_seconds=5,
        max_messages=100,
        markets_limit=5,
        take_profit=0.01,
        stop_loss=0.01,
        max_hold_seconds=10,
    )


def test_mean_reversion_entry_opens_after_sell_streak_in_lower_half() -> None:
    runner = WsSignalRunner(_config())

    assert runner._should_open_mean_reversion(
        best_bid=0.46,
        best_ask=0.47,
        spread=0.01,
        up_streak=0,
        down_streak=3,
        take_profit=0.01,
    )


def test_mean_reversion_entry_rejects_upper_half_prices() -> None:
    runner = WsSignalRunner(_config())

    assert not runner._should_open_mean_reversion(
        best_bid=0.52,
        best_ask=0.53,
        spread=0.01,
        up_streak=0,
        down_streak=4,
        take_profit=0.01,
    )


def test_mean_reversion_exit_uses_bounce_faded() -> None:
    runner = WsSignalRunner(_config())

    assert (
        runner._resolve_exit_reason(
            pnl=0.0,
            hold_seconds=1.0,
            up_streak=2,
            config=_config(),
        )
        == "bounce_faded"
    )
