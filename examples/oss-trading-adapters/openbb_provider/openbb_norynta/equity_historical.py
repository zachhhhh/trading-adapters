from __future__ import annotations

import asyncio
import os
from typing import Any

from norynta import NoryntaClient, NoryntaFrameworkAdapter
from openbb_core.provider.abstract.fetcher import Fetcher
from openbb_core.provider.standard_models.equity_historical import (
    EquityHistoricalData,
    EquityHistoricalQueryParams,
)
from pydantic import Field


class NoryntaEquityHistoricalQueryParams(EquityHistoricalQueryParams):
    """Norynta query where ``symbol`` is an event public key."""

    outcome_index: int = Field(default=0, ge=0, le=255)
    timeframe: str = Field(default="1h", pattern=r"^\d+[mhd]$")
    base_url: str = Field(
        default_factory=lambda: os.getenv(
            "NORYNTA_BASE_URL",
            "https://norynta.com",
        )
    )


class NoryntaEquityHistoricalData(EquityHistoricalData):
    """OpenBB historical price row with Norynta market identity."""

    symbol: str


class NoryntaEquityHistoricalFetcher(
    Fetcher[
        NoryntaEquityHistoricalQueryParams,
        list[NoryntaEquityHistoricalData],
    ]
):
    """Fetch Norynta candles through OpenBB's standard provider lifecycle."""

    @staticmethod
    def transform_query(
        params: dict[str, Any],
    ) -> NoryntaEquityHistoricalQueryParams:
        return NoryntaEquityHistoricalQueryParams(**params)

    @staticmethod
    async def aextract_data(
        query: NoryntaEquityHistoricalQueryParams,
        credentials: dict[str, str] | None,
        **_: Any,
    ) -> list[dict[str, Any]]:
        api_key = (credentials or {}).get("norynta_api_key") or os.getenv(
            "NORYNTA_AGENT_API_KEY"
        )
        adapter = NoryntaFrameworkAdapter(
            NoryntaClient(base_url=query.base_url, api_key=api_key)
        )
        instrument = adapter.instrument(query.symbol, query.outcome_index)
        return await asyncio.to_thread(
            adapter.openbb_rows,
            instrument,
            timeframe=query.timeframe,
            from_time=query.start_date.isoformat() if query.start_date else None,
            to_time=query.end_date.isoformat() if query.end_date else None,
        )

    @staticmethod
    def transform_data(
        query: NoryntaEquityHistoricalQueryParams,
        data: list[dict[str, Any]],
        **_: Any,
    ) -> list[NoryntaEquityHistoricalData]:
        del query
        return [
            NoryntaEquityHistoricalData.model_validate(row)
            for row in data
        ]
