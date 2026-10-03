"""Timelapse record class."""

import struct

from .base import TimestampedRecord, TS_SIZE


class TimelapseRecord(TimestampedRecord):
    """Timelapse record (8 bytes): timestamp only."""

    SIZE = TS_SIZE  # 8 bytes

    def __init__(self, timestamp: int):
        super().__init__(timestamp)

    @classmethod
    def parse(cls, data: bytes, offset: int = 0) -> 'TimelapseRecord':
        """Parse a timelapse record from bytes."""
        timestamp = struct.unpack_from('<q', data, offset)[0]
        return cls(timestamp)

    def to_dict(self) -> dict:
        """Convert record to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp,
        }
