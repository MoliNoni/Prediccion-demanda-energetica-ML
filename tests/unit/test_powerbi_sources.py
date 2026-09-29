from datetime import date
from pathlib import Path
from typing import Any

import pytest

from powerbi.sources import (
    SourceError,
    chunk_date_range,
    fetch_oni,
    fetch_xm_metric,
    parse_oni,
    parse_xm_response,
    with_retry,
)

ONI_SAMPLE = """SEAS  YR   TOTAL  ANOM
 DJF 2023  26.53  -0.71
 JFM 2023  26.94  -0.44
 NDJ 2023  28.54   1.95
 garbage line
"""


def test_chunk_windows_respect_31_day_limit_and_cover_range() -> None:
    windows = chunk_date_range(date(2023, 1, 1), date(2023, 3, 31))

    assert windows[0] == (date(2023, 1, 1), date(2023, 1, 31))
    assert windows[1] == (date(2023, 2, 1), date(2023, 3, 3))
    assert windows[-1][1] == date(2023, 3, 31)
    assert all((end - start).days + 1 <= 31 for start, end in windows)
    for (_, previous_end), (next_start, _) in zip(windows, windows[1:], strict=False):
        assert (next_start - previous_end).days == 1


def test_chunk_single_day_and_invalid_range() -> None:
    assert chunk_date_range(date(2023, 5, 1), date(2023, 5, 1)) == [(date(2023, 5, 1),) * 2]
    with pytest.raises(ValueError):
        chunk_date_range(date(2023, 5, 2), date(2023, 5, 1))


def test_parse_xm_response_converts_string_values() -> None:
    payload = {
        "Items": [
            {"Date": "2023-03-01", "DailyEntities": [{"Id": "Sistema", "Value": "379.74262"}]},
            {"Date": "2023-03-02", "DailyEntities": []},
            {"Date": "2023-03-03", "DailyEntities": [{"Id": "Sistema", "Value": ""}]},
        ]
    }

    assert parse_xm_response(payload) == [(date(2023, 3, 1), 379.74262)]
    assert parse_xm_response({"Items": []}) == []
    assert parse_xm_response({}) == []


def test_parse_xm_response_rejects_bad_values() -> None:
    bad = {"Items": [{"Date": "2023-03-01", "DailyEntities": [{"Id": "Sistema", "Value": "x"}]}]}
    with pytest.raises(SourceError):
        parse_xm_response(bad)


def test_parse_oni_maps_season_to_center_month() -> None:
    frame = parse_oni(ONI_SAMPLE)

    assert frame[["year", "month"]].values.tolist() == [[2023, 1], [2023, 2], [2023, 12]]
    assert frame["oni_anom"].tolist() == [-0.71, -0.44, 1.95]


def test_fetch_xm_metric_uses_cache_and_avoids_second_fetch(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def fake_fetch(url: str, body: dict[str, Any]) -> dict[str, Any]:
        calls.append(body)
        return {
            "Items": [{"Date": "2023-03-01", "DailyEntities": [{"Id": "Sistema", "Value": "1.5"}]}]
        }

    kwargs: dict[str, Any] = {
        "fetch_json": fake_fetch,
        "cache_dir": tmp_path,
        "today": date(2024, 1, 1),
    }
    first = fetch_xm_metric("AporEner", date(2023, 3, 1), date(2023, 3, 10), **kwargs)
    second = fetch_xm_metric("AporEner", date(2023, 3, 1), date(2023, 3, 10), **kwargs)

    assert len(calls) == 1
    assert calls[0]["MetricId"] == "AporEner"
    assert calls[0]["Entity"] == "Sistema"
    assert first["value"].tolist() == second["value"].tolist() == [1.5]
    assert (tmp_path / "AporEner" / "2023-03-01_2023-03-10.json").exists()


def test_fetch_xm_metric_offline_skips_cache_misses(tmp_path: Path) -> None:
    def boom(url: str, body: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("network must not be used")

    frame = fetch_xm_metric(
        "AporEner", date(2023, 3, 1), date(2023, 3, 10),
        fetch_json=boom, cache_dir=tmp_path, use_network=False,
    )  # fmt: skip

    assert frame.empty
    assert list(frame.columns) == ["date", "value"]


def test_fetch_xm_metric_does_not_cache_windows_touching_today(tmp_path: Path) -> None:
    def fake_fetch(url: str, body: dict[str, Any]) -> dict[str, Any]:
        return {"Items": []}

    fetch_xm_metric(
        "AporEner", date(2023, 3, 1), date(2023, 3, 10),
        fetch_json=fake_fetch, cache_dir=tmp_path, today=date(2023, 3, 10),
    )  # fmt: skip

    assert not (tmp_path / "AporEner").exists()


def test_with_retry_recovers_then_fails_after_attempts() -> None:
    state = {"n": 0}

    def flaky() -> str:
        state["n"] += 1
        if state["n"] < 3:
            raise OSError("boom")
        return "ok"

    assert with_retry(flaky, sleep=lambda _: None) == "ok"

    def always_fails() -> str:
        raise OSError("down")

    with pytest.raises(SourceError):
        with_retry(always_fails, sleep=lambda _: None)


def test_fetch_oni_writes_and_reads_cache(tmp_path: Path) -> None:
    online = fetch_oni(fetch_text=lambda url: ONI_SAMPLE, cache_dir=tmp_path, sleep=lambda _: None)
    offline = fetch_oni(cache_dir=tmp_path, use_network=False)
    missing = fetch_oni(cache_dir=tmp_path / "nope", use_network=False)

    assert len(online) == len(offline) == 3
    assert missing.empty
