"""GPS record class."""

import struct
from datetime import datetime, timezone

from .base import TimestampedRecord, TS_SIZE


class GpsRecord(TimestampedRecord):
    """GPS record (53 bytes): timestamp + position data."""

    SIZE = TS_SIZE + 45  # 8 + 45 = 53 bytes

    def __init__(self, timestamp: int, payload: bytes,
                 latitude: float, ns: str, longitude: float, ew: str,
                 speed: float, track: float, altitude: float):
        super().__init__(timestamp)
        self.payload = payload
        self.latitude = latitude
        self.ns = ns
        self.longitude = longitude
        self.ew = ew
        self.speed = speed
        self.track = track
        self.altitude = altitude

    @classmethod
    def parse(cls, data: bytes, offset: int = 0) -> 'GpsRecord':
        """Parse a GPS record from bytes."""
        timestamp = struct.unpack_from('<q', data, offset)[0]

        # Save raw payload
        payload = data[offset + TS_SIZE:offset + cls.SIZE]

        # Parse fields
        pos = offset + TS_SIZE
        # Skip 2 bytes unknown + 1 byte unknown
        pos += 3

        latitude = struct.unpack_from('<d', data, pos)[0]
        pos += 8
        ns = chr(data[pos])
        pos += 1

        longitude = struct.unpack_from('<d', data, pos)[0]
        pos += 8
        ew = chr(data[pos])
        pos += 1

        speed = struct.unpack_from('<d', data, pos)[0]
        pos += 8

        track = struct.unpack_from('<d', data, pos)[0]
        pos += 8

        altitude = struct.unpack_from('<d', data, pos)[0]

        return cls(timestamp, payload, latitude, ns, longitude, ew, speed, track, altitude)

    def get_description(self) -> str:
        """Get human-readable description of GPS data."""
        try:
            time_str = datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat()
        except (OSError, ValueError):
            time_str = str(self.timestamp)

        return (f"time {time_str} position {self.latitude}{self.ns} {self.longitude}{self.ew} "
                f"speed {self.speed} track {self.track} altitude {self.altitude}")

    def to_dict(self) -> dict:
        """Convert record to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp,
            'latitude': self.latitude,
            'ns': self.ns,
            'longitude': self.longitude,
            'ew': self.ew,
            'speed': self.speed,
            'track': self.track,
            'altitude': self.altitude,
            'description': self.get_description(),
        }
