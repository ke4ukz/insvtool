"""Exposure record class."""

import struct

from .base import TimestampedRecord, TS_SIZE


class ExposureRecord(TimestampedRecord):
    """Exposure record (16 bytes): timestamp + shutter speed."""

    SIZE = TS_SIZE + 8  # 8 + 8 = 16 bytes

    def __init__(self, timestamp: int, shutter_speed: float):
        super().__init__(timestamp)
        self.shutter_speed = shutter_speed

    @classmethod
    def parse(cls, data: bytes, offset: int = 0) -> 'ExposureRecord':
        """Parse an exposure record from bytes."""
        timestamp = struct.unpack_from('<q', data, offset)[0]
        shutter_speed = struct.unpack_from('<d', data, offset + TS_SIZE)[0]
        return cls(timestamp, shutter_speed)

    def to_dict(self) -> dict:
        """Convert record to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp,
            'shutterSpeed': self.shutter_speed,
        }
