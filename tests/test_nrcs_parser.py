from providers.nrcs.importer import parse_awdb_data_json


def test_parse_awdb_data_json_converts_imperial():
    payload = """
    [
      {
        "stationTriplet": "301:CA:SNTL",
        "data": [
          {
            "stationElement": {"elementCode": "WTEQ", "storedUnitCode": "in"},
            "values": [{"date": "2026-02-01 12:00", "value": "10"}]
          },
          {
            "stationElement": {"elementCode": "SNWD", "storedUnitCode": "in"},
            "values": [{"date": "2026-02-01 12:00", "value": "40"}]
          },
          {
            "stationElement": {"elementCode": "TOBS", "storedUnitCode": "degF"},
            "values": [{"date": "2026-02-01 12:00", "value": "32"}]
          }
        ]
      }
    ]
    """
    rows = parse_awdb_data_json(payload)
    assert len(rows) == 1
    obs = rows[0]
    assert obs.station_code == "301"
    assert abs(obs.swe_mm - 254.0) < 1e-9
    assert abs(obs.snow_depth_cm - 101.6) < 1e-9
    assert abs(obs.temperature_c - 0.0) < 1e-9
