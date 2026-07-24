from openbb_core.provider.abstract.provider import Provider

from .equity_historical import NoryntaEquityHistoricalFetcher


norynta_provider = Provider(
    name="norynta",
    website="https://norynta.com",
    description="Prediction-market historical prices from Norynta.",
    credentials=["norynta_api_key"],
    fetcher_dict={
        "EquityHistorical": NoryntaEquityHistoricalFetcher,
    },
)
