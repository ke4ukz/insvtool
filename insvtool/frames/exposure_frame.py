"""Exposure frame class for INSV metadata."""

from typing import TYPE_CHECKING

from .timestamped import TimestampedFrame
from .frame_header import FrameHeader
from ..records.exposure import ExposureRecord
from ..records.base import TimestampedRecord

if TYPE_CHECKING:
    from ..metadata import InsvMetadata


class ExposureFrame(TimestampedFrame):
    """Frame containing camera exposure data."""

    def __init__(self, header: FrameHeader, payload: bytes):
        super().__init__(header, payload)

    def _record_size(self, metadata: 'InsvMetadata') -> int:
        """Exposure records have fixed size."""
        return ExposureRecord.SIZE

    def _parse_record(self, data: bytes, offset: int, record_size: int) -> TimestampedRecord:
        """Parse an exposure record."""
        return ExposureRecord.parse(data, offset)
