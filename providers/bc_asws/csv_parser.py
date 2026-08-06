from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class BcAswsCsvMatrix:
    """station_id -> timestamp -> value"""

    values: dict[str, dict[datetime, float]]
    names: dict[str, str]


def parse_bc_asws_csv(text: str) -> BcAswsCsvMatrix:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return BcAswsCsvMatrix(values={}, names={})

    header = _split_csv_line(lines[0])
    if not header or header[0].upper().startswith("DATE") is False:
        # Still try: first column is datetime
        pass

    names: dict[str, str] = {}
    station_ids: list[str | None] = [None]
    for col in header[1:]:
        station_id, name = _parse_station_header(col)
        station_ids.append(station_id)
        if station_id:
            names[station_id] = name or station_id

    values: dict[str, dict[datetime, float]] = {sid: {} for sid in names}

    for line in lines[1:]:
        cols = _split_csv_line(line)
        if not cols:
            continue
        ts = _parse_ts(cols[0])
        if ts is None:
            continue
        for idx in range(1, min(len(cols), len(station_ids))):
            station_id = station_ids[idx]
            if not station_id:
                continue
            cell = cols[idx].strip()
            if cell == "" or cell.upper() in {"NA", "NULL", "M", "-9999"}:
                continue
            try:
                num = float(cell)
            except ValueError:
                continue
            values.setdefault(station_id, {})[ts] = num

    return BcAswsCsvMatrix(values=values, names=names)


def _parse_station_header(col: str) -> tuple[str | None, str | None]:
    text = col.strip().strip('"')
    if not text:
        return None, None
    parts = text.split(None, 1)
    station_id = parts[0]
    name = parts[1] if len(parts) > 1 else station_id
    return station_id, name


def _split_csv_line(line: str) -> list[str]:
    # Province files are simple CSV without embedded commas in station names typically.
    return [c.strip() for c in line.split(",")]


def _parse_ts(value: str) -> datetime | None:
    text = value.strip().strip('"')
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
