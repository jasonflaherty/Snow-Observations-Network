from datetime import datetime, timezone

from providers.jma.parser import (
    dms_pair_to_decimal,
    has_snow_capability,
    iter_hourly_jst_stamps,
    jst_stamp_to_utc,
    parse_amedas_value,
    parse_amedastable,
    parse_map_json,
    utc_to_jst_hour_stamp,
)

def test_dms_pair_to_decimal():
    assert abs(dms_pair_to_decimal([45, 24.9]) - (45 + 24.9 / 60.0)) < 1e-9
    assert abs(dms_pair_to_decimal([141, 40.7]) - (141 + 40.7 / 60.0)) < 1e-9


def test_has_snow_capability():
    assert has_snow_capability("11111111") is True
    assert has_snow_capability("11112110") is True
    assert has_snow_capability("11112010") is False
    assert has_snow_capability("01000000") is False
    assert has_snow_capability("11111") is False


def test_parse_amedas_value_qc():
    assert parse_amedas_value([17.2, 0]) == 17.2
    assert parse_amedas_value([120, 0]) == 120.0
    assert parse_amedas_value([120, 1]) is None
    assert parse_amedas_value(["", 0]) is None
    assert parse_amedas_value(None) is None
    assert parse_amedas_value([None, 0]) is None


def test_jst_stamp_roundtrip():
    stamp = "20260201120000"
    utc = jst_stamp_to_utc(stamp)
    assert utc == datetime(2026, 2, 1, 3, 0, tzinfo=timezone.utc)
    assert utc_to_jst_hour_stamp(utc) == stamp


def test_iter_hourly_jst_stamps():
    start = datetime(2026, 2, 1, 3, 30, tzinfo=timezone.utc)  # 12:30 JST
    end = datetime(2026, 2, 1, 5, 0, tzinfo=timezone.utc)  # 14:00 JST
    stamps = iter_hourly_jst_stamps(start, end)
    assert stamps == ["20260201120000", "20260201130000", "20260201140000"]


def test_parse_amedastable_snow_active():
    payload = {
        "11016": {
            "type": "A",
            "elems": "11111111",
            "lat": [45, 24.9],
            "lon": [141, 40.7],
            "alt": 3,
            "kjName": "稚内",
            "knName": "ワッカナイ",
            "enName": "Wakkanai",
        },
        "11001": {
            "type": "C",
            "elems": "11112010",
            "lat": [45, 31.2],
            "lon": [141, 56.1],
            "alt": 26,
            "kjName": "宗谷岬",
            "knName": "ソウヤミサキ",
            "enName": "Cape Soya",
        },
    }
    stations = parse_amedastable(payload)
    by_code = {s.station_code: s for s in stations}
    wakkanai = by_code["11016"]
    assert wakkanai.active is True
    assert wakkanai.country == "JP"
    assert wakkanai.name == "Wakkanai"
    assert abs(wakkanai.latitude - (45 + 24.9 / 60.0)) < 1e-9
    assert by_code["11001"].active is False


def test_parse_map_json_fields_and_qc():
    stamp_utc = jst_stamp_to_utc("20260201120000")
    payload = {
        "11016": {
            "temp": [ -2.5, 0],
            "snow": [120, 0],
            "snow1h": [3, 0],
            "precipitation1h": [1.5, 0],
            "wind": [4.2, 0],
            "humidity": [85, 0],
        },
        "99999": {
            "snow": [50, 1],  # bad QC
            "temp": ["", 0],
        },
        "88888": {
            "temp": [1.0, 0],
        },
    }
    rows = parse_map_json(
        payload,
        timestamp=stamp_utc,
        station_codes={"11016", "99999", "88888"},
    )
    by_code = {r.station_code: r for r in rows}
    assert "99999" not in by_code  # all fields null after QC
    wak = by_code["11016"]
    assert wak.snow_depth_cm == 120.0
    assert wak.snowfall_cm == 3.0
    assert wak.temperature_c == -2.5
    assert wak.precipitation_mm == 1.5
    assert wak.wind_speed_ms == 4.2
    assert wak.humidity == 85.0
    assert wak.swe_mm is None
    assert wak.quality_flag == "0"
    assert by_code["88888"].temperature_c == 1.0
    assert by_code["88888"].snow_depth_cm is None
