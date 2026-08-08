from providers.bc_asws.csv_parser import parse_bc_asws_csv


def test_parse_bc_asws_csv():
    csv = """DATE(UTC),1A01P Yellowhead Lake,1A02P McBride Upper
2026-02-01 12:00,842,210
2026-02-01 13:00,843,
"""
    matrix = parse_bc_asws_csv(csv)
    assert "1A01P" in matrix.values
    assert matrix.names["1A01P"] == "Yellowhead Lake"
    ts = next(iter(matrix.values["1A01P"]))
    assert matrix.values["1A01P"][ts] == 842.0
    assert len(matrix.values["1A02P"]) == 1
