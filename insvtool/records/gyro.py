"""Gyroscope record classes."""

import struct
from typing import List

from .base import TimestampedRecord, TS_SIZE


class GyroV1Record(TimestampedRecord):
    """Gyroscope record version 1 (56 bytes): timestamp + 6 doubles."""

    SIZE = TS_SIZE + 6 * 8  # 8 + 48 = 56 bytes

    def __init__(self, timestamp: int, payload: List[float]):
        super().__init__(timestamp)
        self.payload = payload

    @classmethod
    def parse(cls, data: bytes, offset: int = 0) -> 'GyroV1Record':
        """Parse a GyroV1 record from bytes."""
        timestamp = struct.unpack_from('<q', data, offset)[0]
        payload = list(struct.unpack_from('<6d', data, offset + TS_SIZE))
        return cls(timestamp, payload)

    def to_dict(self) -> dict:
        """Convert record to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp,
            'payload': self.payload,
        }


class GyroV2Record(TimestampedRecord):
    """Gyroscope record version 2 (20 bytes): timestamp + 6 shorts."""

    SIZE = TS_SIZE + 6 * 2  # 8 + 12 = 20 bytes

    def __init__(self, timestamp: int, payload: List[int]):
        super().__init__(timestamp)
        self.payload = payload

    @classmethod
    def parse(cls, data: bytes, offset: int = 0) -> 'GyroV2Record':
        """Parse a GyroV2 record from bytes."""
        timestamp = struct.unpack_from('<q', data, offset)[0]
        payload = list(struct.unpack_from('<6h', data, offset + TS_SIZE))
        return cls(timestamp, payload)

    def to_dict(self) -> dict:
        """Convert record to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp,
            'payload': self.payload,
        }


class GyroRawRecord(TimestampedRecord):
    """Gyroscope record with unknown format (raw bytes)."""

    def __init__(self, timestamp: int, payload: bytes):
        super().__init__(timestamp)
        self.payload = payload
        self.size = TS_SIZE + len(payload)

    @classmethod
    def parse(cls, data: bytes, record_size: int, offset: int = 0) -> 'GyroRawRecord':
        """Parse a raw gyro record from bytes."""
        timestamp = struct.unpack_from('<q', data, offset)[0]
        payload_size = record_size - TS_SIZE
        payload = data[offset + TS_SIZE:offset + TS_SIZE + payload_size]
        return cls(timestamp, payload)

    def to_dict(self) -> dict:
        """Convert record to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp,
            'payload': self.payload.hex(),
        }
