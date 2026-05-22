from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    polymarket_pk: str = ""
    polymarket_funder: str = ""
    polymarket_signature_type: int = 0
    polymarket_host: str = "https://clob.polymarket.com"
    polymarket_chain_id: int = 137
    symbols: str = "BTC,ETH"
    scan_interval_seconds: int = 2
    markets_refresh_seconds: int = 30
    min_edge_bps: int = 30
    max_position_usd: float = 100.0
    max_open_exposure_usd: float = 500.0
    slippage_bps: float = 5.0
    gas_estimate_usd: float = 0.01
    paper_trading: bool = True
    paper_starting_balance_usd: float = 1000.0
    preorder_enabled: bool = False
    preorder_target_price_up: float = 0.49
    preorder_target_price_down: float = 0.49
    preorder_max_bundle_cost: float = 0.98
    preorder_partial_exit_price: float = 0.47
    mm_enabled: bool = False
    mm_spread_bps: float = 100.0
    mm_order_size: float = 10.0
    mm_reprice_threshold_bps: float = 10.0
    mm_max_inventory_per_market: float = 50.0
    mm_markets_limit: int = 5
    mm_ws_enabled: bool = False
    mm_ws_runtime_seconds: int = 15
    mm_ws_max_messages: int = 200
    mm_reward_per_fill_usd: float = 0.0
    mm_reward_only_mode: bool = False
    mm_max_unrealized_loss_usd: float = 0.0
    pair_mm_enabled: bool = False
    pair_mm_markets_limit: int = 5
    pair_mm_target_pairs: float = 5.0
    pair_mm_quote_edge: float = 0.01
    pair_mm_skew_step: float = 0.01
    pair_mm_max_skew: float = 3.0
    pair_mm_reward_per_trade_usd: float = 0.0
    ws_signal_enabled: bool = False
    ws_signal_runtime_seconds: int = 5
    ws_signal_max_messages: int = 100
    ws_signal_markets_limit: int = 5
    ws_signal_take_profit: float = 0.01
    ws_signal_stop_loss: float = 0.01
    ws_signal_max_hold_seconds: int = 10
    db_path: str = "data/poly_market_arb.db"
    log_level: str = "INFO"

    @field_validator("polymarket_signature_type")
    @classmethod
    def _validate_sig_type(cls, value: int) -> int:
        if value not in (0, 1, 2):
            raise ValueError("POLYMARKET_SIGNATURE_TYPE must be 0, 1, or 2")
        return value

    @property
    def db_full_path(self) -> Path:
        path = Path(self.db_path)
        return path if path.is_absolute() else REPO_ROOT / path

    def normalized_symbols(self) -> tuple[str, ...]:
        return tuple(part.strip().upper() for part in self.symbols.split(",") if part.strip())

    def assert_polymarket_ready(self) -> None:
        if not self.polymarket_pk:
            raise RuntimeError("POLYMARKET_PK is empty — set it in .env")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
