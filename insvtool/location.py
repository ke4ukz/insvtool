"""Extract the first active GPS fix from INSV metadata."""

import math
import re
import struct
from typing import Optional

from .frames.frame_types import FrameType
from .metadata import InsvMetadata
from .records.gps import GpsRecord


TIME_PATTERN = re.compile(r'[+-]?(?:\d+(?:\.\d+)?|\d+:[0-5]\d:[0-5]\d(?:\.\d+)?)\Z')


def parse_location_time(value: str) -> float:
    """Parse seconds or h:mm:ss.fff, preserving negative zero."""
    if not TIME_PATTERN.fullmatch(value):
        raise ValueError('location time must be decimal seconds or h:mm:ss.fff')
    parts = value.lstrip('+-').split(':')
    seconds = float(parts[0]) if len(parts) == 1 else (
        int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2]))
    if not math.isfinite(seconds):
        raise ValueError('location time must be finite')
    return -seconds if value.startswith('-') else seconds


def find_location(metadata: InsvMetadata, time_offset: float = 0.0) -> Optional[dict]:
    """Return decimal coordinates and a map link, or None without an active fix.

    GPS payload byte 2 is the NMEA-style status: A = active, V = void.
    This indicates fix validity, not a measured accuracy or confidence score.
    """
    from_end = math.copysign(1, time_offset) < 0
    info = metadata.find_frame(FrameType.INFO)
    start_ms = None
    duration = None
    if info is not None:
        info.parse(metadata)
        extra = info.extra_metadata
        if extra.HasField('FirstGpsTimestamp') and extra.FirstGpsTimestamp > 0:
            start_ms = extra.FirstGpsTimestamp
        if extra.HasField('TotalTime') and extra.TotalTime >= 0:
            duration = extra.TotalTime
    if (time_offset != 0 or from_end) and start_ms is None:
        raise ValueError('Timed location lookup requires FirstGpsTimestamp metadata')
    target_seconds = time_offset
    if from_end:
        if duration is None:
            raise ValueError('End-relative location lookup requires TotalTime metadata')
        target_seconds = duration + time_offset
    if target_seconds < 0 or (duration is not None and target_seconds > duration):
        raise ValueError('Location time is outside the video duration')
    target_ms = None if start_ms is None else start_ms + target_seconds * 1000
    best = None
    best_distance = float('inf')
    for frame in metadata.frames:
        if frame.header.frame_type != FrameType.GPS:
            continue
        for offset in range(0, len(frame.payload) - GpsRecord.SIZE + 1, GpsRecord.SIZE):
            record = GpsRecord.parse(frame.payload, offset)
            # The first 8 bytes contain two uint32s, not an int64 clock.
            # The first is Unix seconds; payload bytes 0..1 are milliseconds.
            seconds = struct.unpack_from('<I', frame.payload, offset)[0]
            millis = struct.unpack_from('<H', record.payload)[0]
            if millis >= 1000:
                continue
            timestamp_ms = seconds * 1000 + millis
            if target_ms is None:
                target_ms = timestamp_ms  # Untimed lookup without INFO metadata.
            distance = abs(timestamp_ms - target_ms)
            if distance > 60_000 or distance >= best_distance:
                continue
            if record.payload[2:3] != b'A':
                continue
            if record.ns not in ('N', 'S') or record.ew not in ('E', 'W', 'O'):
                continue
            latitude, longitude = abs(record.latitude), abs(record.longitude)
            if not (math.isfinite(latitude) and math.isfinite(longitude)):
                continue
            if latitude > 90 or longitude > 180:
                continue
            if record.ns == 'S':
                latitude = -latitude
            if record.ew != 'E':
                longitude = -longitude
            best_distance = distance
            best = {
                'latitude': latitude,
                'longitude': longitude,
                'mapUrl': (
                    f'https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}'
                    f'#map=16/{latitude}/{longitude}'
                ),
            }
    return best
