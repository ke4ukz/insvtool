"""GPS frame class for INSV metadata."""

from typing import TYPE_CHECKING

from .timestamped import TimestampedFrame
from .frame_header import FrameHeader
from ..records.gps import GpsRecord
from ..records.base import TimestampedRecord

if TYPE_CHECKING:
    from ..metadata import InsvMetadata


class GpsFrame(TimestampedFrame):
    """Frame containing GPS location data."""

    def __init__(self, header: FrameHeader, payload: bytes):
        super().__init__(header, payload)

    def _record_size(self, metadata: 'InsvMetadata') -> int:
        """GPS records have fixed size."""
        return GpsRecord.SIZE

    def _parse_record(self, data: bytes, offset: int, record_size: int) -> TimestampedRecord:
        """Parse a GPS record."""
        return GpsRecord.parse(data, offset)
