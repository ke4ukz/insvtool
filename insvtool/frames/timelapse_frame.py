"""Timelapse frame class for INSV metadata."""

from typing import TYPE_CHECKING

from .timestamped import TimestampedFrame
from .frame_header import FrameHeader
from ..records.timelapse import TimelapseRecord
from ..records.base import TimestampedRecord

if TYPE_CHECKING:
    from ..metadata import InsvMetadata


class TimelapseFrame(TimestampedFrame):
    """Frame containing timelapse timestamp mapping."""

    def __init__(self, header: FrameHeader, payload: bytes):
        super().__init__(header, payload)

    def _record_size(self, metadata: 'InsvMetadata') -> int:
        """Timelapse records have fixed size."""
        return TimelapseRecord.SIZE

    def _parse_record(self, data: bytes, offset: int, record_size: int) -> TimestampedRecord:
        """Parse a timelapse record."""
        return TimelapseRecord.parse(data, offset)
