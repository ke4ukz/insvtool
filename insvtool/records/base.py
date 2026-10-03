"""Base class for timestamped records."""

import struct
from typing import BinaryIO


TS_SIZE = 8  # 8 bytes for timestamp (long)


class TimestampedRecord:
    """Base class for records with a timestamp."""

    def __init__(self, timestamp: int):
        self.timestamp = timestamp

    def to_dict(self) -> dict:
        """Convert record to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp,
        }
