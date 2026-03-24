"""Portfolio and watchlist manager — reads/writes data/portfolio.json and data/watchlist.json."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Resolve paths relative to project root (this file is claw/tools/portfolio_manager.py)
_PROJECT_ROOT = Path(__file__).parent.parent.parent
PORTFOLIO_PATH = _PROJECT_ROOT / "data" / "portfolio.json"
WATCHLIST_PATH = _PROJECT_ROOT / "data" / "watchlist.json"


# ── Portfolio ──────────────────────────────────────────────────────────────


class PortfolioManager:
    """
    CRUD for user's stock holdings and daily watchlist history.

    portfolio.json schema:
    {
      "updated_at": "ISO datetime",
      "holdings": [
        {
          "symbol": "2330",
          "name": "台積電",
          "shares": 1000,          # 股 (not 張; 1張=1000股)
          "cost_per_share": 850.0,
          "purchase_date": "2025-01-15",
          "note": ""
        }
      ]
    }

    watchlist.json schema:
    {
      "last_updated": "ISO datetime",
      "history": [
        {
          "date": "2026-03-23",
          "top5": [
            {"symbol":"2330","name":"台積電","signal":"buy","rsi":55.2,"summary":"..."}
          ]
        }
      ]
    }
    """

    # ── Portfolio CRUD ─────────────────────────────────────────────────────

    def _load(self) -> dict:
        """Load portfolio.json, return empty structure on missing/corrupt file."""
        try:
            PORTFOLIO_PATH.parent.mkdir(parents=True, exist_ok=True)
            if PORTFOLIO_PATH.exists():
                with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "holdings" not in data:
                        data["holdings"] = []
                    return data
        except Exception as e:
            logger.warning(f"[Portfolio] Load failed: {e}")
        return {"updated_at": "", "holdings": []}

    def _save(self, data: dict) -> None:
        """Write portfolio.json atomically."""
        data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        PORTFOLIO_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PORTFOLIO_PATH.with_suffix(".json.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp.replace(PORTFOLIO_PATH)
        except Exception as e:
            logger.error(f"[Portfolio] Save failed: {e}")
            tmp.unlink(missing_ok=True)
            raise

    def get_holdings(self) -> list[dict]:
        """Return all holdings."""
        return self._load().get("holdings", [])

    def add_holding(
        self,
        symbol: str,
        name: str = "",
        shares: int = 0,
        cost_per_share: float = 0.0,
        purchase_date: str = "",
        note: str = "",
    ) -> dict:
        """
        Add or update a holding. If symbol already exists, overwrites it.

        Returns the saved holding dict.
        """
        data = self._load()
        holdings = data["holdings"]

        holding = {
            "symbol": symbol.strip(),
            "name": name.strip() or symbol.strip(),
            "shares": max(0, int(shares)),
            "cost_per_share": max(0.0, float(cost_per_share)),
            "purchase_date": purchase_date.strip() or date.today().isoformat(),
            "note": note.strip(),
        }

        # Replace if exists
        idx = next((i for i, h in enumerate(holdings) if h["symbol"] == symbol), None)
        if idx is not None:
            holdings[idx] = holding
        else:
            holdings.append(holding)

        self._save(data)
        logger.info(f"[Portfolio] Saved holding: {holding}")
        return holding

    def remove_holding(self, symbol: str) -> bool:
        """Remove a holding by symbol. Returns True if found and removed."""
        data = self._load()
        before = len(data["holdings"])
        data["holdings"] = [h for h in data["holdings"] if h["symbol"] != symbol]
        if len(data["holdings"]) < before:
            self._save(data)
            logger.info(f"[Portfolio] Removed holding: {symbol}")
            return True
        return False

    def update_holding(self, symbol: str, **kwargs) -> Optional[dict]:
        """Partially update a holding's fields. Returns updated holding or None."""
        data = self._load()
        for h in data["holdings"]:
            if h["symbol"] == symbol:
                for k, v in kwargs.items():
                    if k in h:
                        h[k] = v
                self._save(data)
                return h
        return None

    def get_holding(self, symbol: str) -> Optional[dict]:
        """Return single holding by symbol, or None."""
        for h in self.get_holdings():
            if h["symbol"] == symbol:
                return h
        return None

    def portfolio_summary(self, prices: dict[str, float]) -> list[dict]:
        """
        Compute P&L for each holding given a dict of {symbol: current_price}.

        Returns list of enriched holding dicts with:
          current_price, gain_amount, gain_pct, market_value
        """
        result = []
        for h in self.get_holdings():
            sym = h["symbol"]
            current = prices.get(sym)
            row = dict(h)
            if current is not None:
                cost = h["cost_per_share"]
                row["current_price"] = current
                row["gain_amount"] = round((current - cost) * h["shares"], 2)
                row["gain_pct"] = round((current - cost) / cost * 100, 2) if cost else 0.0
                row["market_value"] = round(current * h["shares"], 2)
            result.append(row)
        return result

    # ── Watchlist ──────────────────────────────────────────────────────────

    def _load_watchlist(self) -> dict:
        try:
            WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
            if WATCHLIST_PATH.exists():
                with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "history" not in data:
                        data["history"] = []
                    return data
        except Exception as e:
            logger.warning(f"[Watchlist] Load failed: {e}")
        return {"last_updated": "", "history": []}

    def _save_watchlist(self, data: dict) -> None:
        data["last_updated"] = datetime.now().isoformat(timespec="seconds")
        WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = WATCHLIST_PATH.with_suffix(".json.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp.replace(WATCHLIST_PATH)
        except Exception as e:
            logger.error(f"[Watchlist] Save failed: {e}")
            tmp.unlink(missing_ok=True)
            raise

    def save_watchlist_entry(self, entry_date: str, top5: list[dict]) -> None:
        """
        Append or overwrite today's top5 entry in watchlist history.

        Args:
            entry_date: "YYYY-MM-DD"
            top5: list of {symbol, name, signal, rsi, summary}
        """
        data = self._load_watchlist()
        history = data["history"]

        entry = {"date": entry_date, "top5": top5}

        # Replace if same date exists
        idx = next((i for i, e in enumerate(history) if e.get("date") == entry_date), None)
        if idx is not None:
            history[idx] = entry
        else:
            history.append(entry)

        # Keep last 90 days
        history.sort(key=lambda e: e.get("date", ""), reverse=True)
        data["history"] = history[:90]

        self._save_watchlist(data)
        logger.info(f"[Watchlist] Saved entry for {entry_date}: {len(top5)} stocks")

    def get_latest_top5(self) -> list[dict]:
        """Return the most recent top5 list, or [] if empty."""
        history = self._load_watchlist().get("history", [])
        if not history:
            return []
        history.sort(key=lambda e: e.get("date", ""), reverse=True)
        return history[0].get("top5", [])

    def get_watchlist_history(self, days: int = 7) -> list[dict]:
        """Return last N days of watchlist history."""
        history = self._load_watchlist().get("history", [])
        history.sort(key=lambda e: e.get("date", ""), reverse=True)
        return history[:days]
