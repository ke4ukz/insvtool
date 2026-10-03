"""Gyroscope frame class for INSV metadata."""

from typing import TYPE_CHECKING

from .timestamped import TimestampedFrame
from .frame_header import FrameHeader
from .frame_types import FrameType
from ..records.gyro import GyroV1Record, GyroV2Record, GyroRawRecord
from ..records.base import TimestampedRecord

if TYPE_CHECKING:
    from ..metadata import InsvMetadata


class GyroFrame(TimestampedFrame):
    """Frame containing gyroscope sensor data."""

    def __init__(self, header: FrameHeader, payload: bytes):
        super().__init__(header, payload)
        self._record_size_value = 0

    def _record_size(self, metadata: 'InsvMetadata') -> int:
        """Get record size from INFO frame's embedded gyro data."""
        if self._record_size_value > 0:
            return self._record_size_value

        # Find INFO frame to determine gyro record size
        from .info_frame import InfoFrame
        info_frame = metadata.find_frame(FrameType.INFO)

        if info_frame is None or not isinstance(info_frame, InfoFrame):
            return 0

        if not info_frame.parsed:
            return 0

        self._record_size_value = info_frame.get_gyro_record_size()
        return self._record_size_value

    def _parse_record(self, data: bytes, offset: int, record_size: int) -> TimestampedRecord:
        """Parse a gyro record based on size."""
        if record_size == GyroV1Record.SIZE:
            return GyroV1Record.parse(data, offset)
        elif record_size == GyroV2Record.SIZE:
            return GyroV2Record.parse(data, offset)
        else:
            return GyroRawRecord.parse(data, record_size, offset)
