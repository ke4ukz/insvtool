"""Base class for frames containing timestamped records."""

from typing import List, TYPE_CHECKING

from .frame import Frame
from .frame_header import FrameHeader
from ..records.base import TimestampedRecord

if TYPE_CHECKING:
    from ..metadata import InsvMetadata


class TimestampedFrame(Frame):
    """Base class for frames containing a list of timestamped records."""

    def __init__(self, header: FrameHeader, payload: bytes):
        super().__init__(header, payload)
        self.records: List[TimestampedRecord] = []

    def _parse_internal(self, metadata: 'InsvMetadata') -> bool:
        """Parse records from payload."""
        record_size = self._record_size(metadata)
        if record_size <= 0:
            return False

        offset = 0
        while offset + record_size <= len(self.payload):
            record = self._parse_record(self.payload, offset, record_size)
            self.records.append(record)
            offset += record_size

        return True

    def _record_size(self, metadata: 'InsvMetadata') -> int:
        """Return the size of each record. Override in subclasses."""
        raise NotImplementedError

    def _parse_record(self, data: bytes, offset: int, record_size: int) -> TimestampedRecord:
        """Parse a single record from data. Override in subclasses."""
        raise NotImplementedError

    def to_dict(self) -> dict:
        """Convert frame to dictionary for JSON serialization."""
        result = super().to_dict()
        if self.parsed:
            result['records'] = [r.to_dict() for r in self.records]
        return result
