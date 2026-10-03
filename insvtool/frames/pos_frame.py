"""POS frame class for drone position/telemetry data."""

from typing import TYPE_CHECKING

from .timestamped import TimestampedFrame
from .frame_header import FrameHeader
from ..records.pos import PosRecord
from ..records.base import TimestampedRecord

if TYPE_CHECKING:
    from ..metadata import InsvMetadata


class PosFrame(TimestampedFrame):
    """
    Frame containing drone position and telemetry data.

    Found in drone recordings (e.g., Antigravity A1).
    Contains position relative to home point, velocities, and AGL.
    """

    def __init__(self, header: FrameHeader, payload: bytes):
        super().__init__(header, payload)

    def _record_size(self, metadata: 'InsvMetadata') -> int:
        """POS records have fixed size of 44 bytes."""
        return PosRecord.SIZE

    def _parse_record(self, data: bytes, offset: int, record_size: int) -> TimestampedRecord:
        """Parse a POS record."""
        return PosRecord.parse(data, offset)
