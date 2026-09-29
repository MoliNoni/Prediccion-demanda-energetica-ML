"""External data sources for the Power BI dataset (XM public API and NOAA ONI).

All network access goes through injectable callables so tests never hit the network.
Raw XM responses are cached on disk, which makes reruns incremental and cheap.
"""

import json
import logging
import time
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib import request

import pandas as pd

logger = logging.getLogger(__name__)

XM_DAILY_URL = "https://servapibi.xm.com.co/daily"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
XM_MAX_DAYS = 31
DEFAULT_CACHE_DIR = Path("data/powerbi/cache")

# XM metric id -> column name in the market fact table.
XM_METRICS: dict[str, str] = {
    "PPPrecBolsNaci": "spot_price_cop_kwh",
    "PorcVoluUtilDiar": "reservoir_fraction",
    "AporEner": "inflows_kwh",
}

SEASON_CENTER_MONTH: dict[str, int] = {
    season: month
    for month, season in enumerate(
        ("DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"),
        start=1,
    )
}

FetchJson = Callable[[str, dict[str, Any]], dict[str, Any]]
FetchText = Callable[[str], str]


class SourceError(RuntimeError):
    """Raised when an external source cannot be read or parsed."""


def _open(req: request.Request, timeout: float) -> bytes:
    if req.get_full_url().split(":", 1)[0] != "https":
        raise SourceError("Only https URLs are allowed")
    with request.urlopen(req, timeout=timeout) as response:  # noqa: S310
        return response.read()


def http_post_json(url: str, body: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    req = request.Request(  # noqa: S310
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    return json.loads(_open(req, timeout).decode("utf-8"))


def http_get_text(url: str, timeout: float = 30.0) -> str:
    req = request.Request(url, method="GET")  # noqa: S310
    return _open(req, timeout).decode("utf-8")


def with_retry[T](
    operation: Callable[[], T],
    *,
    attempts: int = 3,
    backoff: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run ``operation`` up to ``attempts`` times with exponential backoff."""
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except (OSError, ValueError) as error:
            if attempt == attempts:
                raise SourceError(f"Operation failed after {attempts} attempts: {error}") from error
            logger.warning("Attempt %s/%s failed: %s", attempt, attempts, error)
            sleep(backoff * 2 ** (attempt - 1))
    raise AssertionError("unreachable")  # pragma: no cover


def chunk_date_range(
    start: date, end: date, max_days: int = XM_MAX_DAYS
) -> list[tuple[date, date]]:
    """Split an inclusive date range into consecutive windows of at most ``max_days``."""
    if end < start:
        raise ValueError("end must not be before start")
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=max_days - 1), end)
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def parse_xm_response(payload: dict[str, Any]) -> list[tuple[date, float]]:
    """Extract ``(date, value)`` pairs; values arrive as strings, empty items are skipped."""
    rows: list[tuple[date, float]] = []
    for item in payload.get("Items") or []:
        entities = item.get("DailyEntities") or []
        if not entities:
            continue
        entity = next((e for e in entities if e.get("Id") == "Sistema"), entities[0])
        raw_value = entity.get("Value")
        if raw_value in (None, ""):
            continue
        try:
            rows.append((date.fromisoformat(str(item["Date"])[:10]), float(raw_value)))
        except (KeyError, ValueError) as error:
            raise SourceError(f"Unparseable XM item: {item!r}") from error
    return rows


def fetch_xm_metric(
    metric: str,
    start: date,
    end: date,
    *,
    fetch_json: FetchJson = http_post_json,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    use_network: bool = True,
    today: date | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> pd.DataFrame:
    """Return a ``date, value`` frame for one XM metric, reading cached windows first."""
    today = today or date.today()
    rows: list[tuple[date, float]] = []
    for window_start, window_end in chunk_date_range(start, end):
        cache_file = cache_dir / metric / f"{window_start}_{window_end}.json"
        if cache_file.exists():
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
        elif not use_network:
            logger.warning(
                "Cache miss for %s %s..%s (network disabled)", metric, window_start, window_end
            )
            continue
        else:
            body = {
                "MetricId": metric,
                "StartDate": window_start.isoformat(),
                "EndDate": window_end.isoformat(),
                "Entity": "Sistema",
                "Filter": [],
            }
            payload = with_retry(lambda body=body: fetch_json(XM_DAILY_URL, body), sleep=sleep)
            if window_end < today:  # windows touching today may still be incomplete
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(payload), encoding="utf-8")
        rows.extend(parse_xm_response(payload))
    frame = pd.DataFrame(rows, columns=["date", "value"])
    return frame.drop_duplicates("date", keep="last").sort_values("date", ignore_index=True)


def enso_phase(anomaly: float) -> str:
    if anomaly >= 0.5:
        return "El Niño"
    if anomaly <= -0.5:
        return "La Niña"
    return "Neutral"


def parse_oni(text: str) -> pd.DataFrame:
    """Parse the NOAA ``oni.ascii.txt`` table into ``year, month, oni_anom`` rows."""
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0] not in SEASON_CENTER_MONTH:
            continue
        try:
            year = int(parts[1])
            anomaly = float(parts[3])
        except ValueError as error:
            raise SourceError(f"Unparseable ONI line: {line!r}") from error
        rows.append({"year": year, "month": SEASON_CENTER_MONTH[parts[0]], "oni_anom": anomaly})
    return pd.DataFrame(rows, columns=["year", "month", "oni_anom"])


def fetch_oni(
    *,
    fetch_text: FetchText = http_get_text,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    use_network: bool = True,
    sleep: Callable[[float], None] = time.sleep,
) -> pd.DataFrame:
    """Return the ONI table; the raw text is cached and refreshed whenever the network is on."""
    cache_file = cache_dir / "oni.txt"
    if use_network:
        text = with_retry(lambda: fetch_text(ONI_URL), sleep=sleep)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(text, encoding="utf-8")
    elif cache_file.exists():
        text = cache_file.read_text(encoding="utf-8")
    else:
        logger.warning("ONI cache missing and network disabled; dim_enso_monthly will be empty")
        return pd.DataFrame(columns=["year", "month", "oni_anom"])
    return parse_oni(text)
