from __future__ import annotations

from datetime import datetime

from AlgorithmImports import (
    FileFormat,
    PythonData,
    SubscriptionDataSource,
    SubscriptionTransportMedium,
)


class NoryntaQuote(PythonData):
    """LEAN custom-data reader for `norynta-adapters export lean` CSV files."""

    source_path = "data/norynta-lean.csv"

    def get_source(self, config, date, is_live_mode):
        del config, date, is_live_mode
        return SubscriptionDataSource(
            self.source_path,
            SubscriptionTransportMedium.LOCAL_FILE,
            FileFormat.CSV,
        )

    def reader(self, config, line, date, is_live_mode):
        del date, is_live_mode
        if not line or line.startswith("time,"):
            return None
        fields = line.split(",")
        quote = NoryntaQuote()
        quote.symbol = config.symbol
        quote.time = datetime.fromisoformat(fields[0].replace("Z", "+00:00"))
        quote["bid"] = float(fields[2])
        quote["ask"] = float(fields[3])
        quote["bid_size"] = float(fields[4])
        quote["ask_size"] = float(fields[5])
        quote["sequence"] = fields[6]
        quote.value = (quote["bid"] + quote["ask"]) / 2
        return quote
