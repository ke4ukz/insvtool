"""Extract the first active GPS fix from INSV metadata."""

import math
from typing import Optional

from .frames.frame_types import FrameType
from .metadata import InsvMetadata
from .records.gps import GpsRecord


def find_location(metadata: InsvMetadata) -> Optional[dict]:
    """Return decimal coordinates and a map link, or None without an active fix.

    GPS payload byte 2 is the NMEA-style status: A = active, V = void.
    This indicates fix validity, not a measured accuracy or confidence score.
    """
    for frame in metadata.frames:
        if frame.header.frame_type != FrameType.GPS:
            continue
        for offset in range(0, len(frame.payload) - GpsRecord.SIZE + 1, GpsRecord.SIZE):
            record = GpsRecord.parse(frame.payload, offset)
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
            return {
                'latitude': latitude,
                'longitude': longitude,
                'mapUrl': (
                    f'https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}'
                    f'#map=16/{latitude}/{longitude}'
                ),
            }
    return None
