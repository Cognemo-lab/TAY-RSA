from __future__ import annotations

import binascii
import sqlite3
from pathlib import Path
from typing import Any


def _blob_to_text_or_hex(value: bytes) -> str:
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        return "0x" + binascii.hexlify(value).decode("ascii")
    if all(ch.isprintable() or ch.isspace() for ch in text):
        return text
    return "0x" + binascii.hexlify(value).decode("ascii")


def _coerce(value: Any) -> Any:
    if isinstance(value, bytes):
        return _blob_to_text_or_hex(value)
    return value


def read_mwi_metadata(path: str | Path) -> dict[str, Any]:
    """Read metadata from a MindWare ``.mwi`` SQLite index file.

    The paired ``.mwx`` contains the signal packets. The ``.mwi`` file stores
    acquisition metadata, channel labels, calibration post-processing records,
    and packet offsets into the raw data stream.
    """

    path = Path(path)
    con = sqlite3.connect(f"file:{path.resolve()}?immutable=1", uri=True)
    con.row_factory = sqlite3.Row
    try:
        info = _one(con, "select * from file_information")
        channels = _rows(
            con,
            """
            select c.channel_id, c.channel_group_id, pc.channel_number,
                   c.label, pc.label as physical_label, c.disabled,
                   c.interleav_index
            from channel c
            left join physical_channel pc on pc.channel_id = c.physical_channel_id
            order by c.channel_id
            """,
        )
        channel_groups = _rows(con, "select * from channel_group order by group_id")
        devices = _rows(con, "select * from device order by device_id")
        data_ranges = _rows(
            con,
            """
            select channel_group_id, count(*) as packet_count,
                   min(start_time_offset) as start_tick,
                   max(end_time_offset) as end_tick
            from data
            group by channel_group_id
            order by channel_group_id
            """,
        )
        events = _rows(
            con,
            """
            select e.event_id, es.label, e.event_time
            from event e
            left join event_source es on es.event_source_id = e.event_source_id
            order by e.event_time
            """,
        )
    finally:
        con.close()

    time_base = info.get("time_base") or 1
    for row in data_ranges:
        row["duration_s"] = (row["end_tick"] - row["start_tick"] + 1) / time_base

    return {
        "path": str(path),
        "file_information": info,
        "devices": devices,
        "channels": channels,
        "channel_groups": channel_groups,
        "data_ranges": data_ranges,
        "events": events,
    }


def _one(con: sqlite3.Connection, sql: str) -> dict[str, Any]:
    row = con.execute(sql).fetchone()
    return {k: _coerce(row[k]) for k in row.keys()} if row else {}


def _rows(con: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    rows = con.execute(sql).fetchall()
    return [{k: _coerce(row[k]) for k in row.keys()} for row in rows]
