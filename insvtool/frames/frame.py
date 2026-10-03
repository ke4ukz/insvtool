"""Base Frame class for INSV metadata."""

from typing import BinaryIO, TYPE_CHECKING

from .frame_header import FrameHeader, FRAME_HEADER_SIZE
from .frame_types import FrameType

if TYPE_CHECKING:
    from ..metadata import InsvMetadata


class Frame:
    """Base class for all INSV frame types."""

    def __init__(self, header: FrameHeader, payload: bytes):
        self.header = header
        self.payload = payload
        self.parsed = False

    @classmethod
    def read(cls, file: BinaryIO, header: FrameHeader) -> 'Frame':
        """
        Read frame data from file based on header information.

        Args:
            file: Open file in binary mode
            header: Frame header with position and size info

        Returns:
            Frame instance (or appropriate subclass)
        """
        file.seek(header.frame_pos)
        payload = file.read(header.frame_size)

        # Import here to avoid circular imports
        from .index_frame import IndexFrame
        from .info_frame import InfoFrame
        from .gyro_frame import GyroFrame
        from .gps_frame import GpsFrame
        from .exposure_frame import ExposureFrame
        from .timelapse_frame import TimelapseFrame
        from .pos_frame import PosFrame

        # Create appropriate frame subclass based on type
        if header.frame_type == FrameType.INDEX:
            return IndexFrame(header, payload)
        elif header.frame_type == FrameType.INFO:
            return InfoFrame(header, payload)
        elif header.frame_type == FrameType.GYRO:
            return GyroFrame(header, payload)
        elif header.frame_type == FrameType.GPS:
            return GpsFrame(header, payload)
        elif header.frame_type == FrameType.EXPOSURE:
            return ExposureFrame(header, payload)
        elif header.frame_type == FrameType.TIMELAPSE:
            return TimelapseFrame(header, payload)
        elif header.frame_type == FrameType.POS:
            return PosFrame(header, payload)
        else:
            return Frame(header, payload)

    @classmethod
    def read_raw(cls, file: BinaryIO, from_pos: int, to_pos: int) -> 'Frame':
        """
        Read raw frame data between two positions.

        Used for unknown/unparsed data between known frames.

        Args:
            file: Open file in binary mode
            from_pos: Start position
            to_pos: End position

        Returns:
            Frame with RAW type
        """
        size = to_pos - from_pos
        header = FrameHeader(FrameType.RAW.value, 0, size, from_pos)
        file.seek(from_pos)
        payload = file.read(size)
        return Frame(header, payload)

    def parse(self, metadata: 'InsvMetadata') -> bool:
        """
        Parse the frame payload.

        Args:
            metadata: Parent metadata object (may be needed for context)

        Returns:
            True if parsing succeeded
        """
        if self.parsed:
            return True

        self.parsed = self._parse_internal(metadata)
        return self.parsed

    def _parse_internal(self, metadata: 'InsvMetadata') -> bool:
        """
        Internal parsing implementation. Override in subclasses.

        Args:
            metadata: Parent metadata object

        Returns:
            True if parsing succeeded
        """
        # Base implementation does nothing
        return False

    def to_dict(self) -> dict:
        """Convert frame to dictionary for JSON serialization."""
        result = {
            'header': self.header.to_dict(),
            'parsed': self.parsed,
        }
        return result

    def __repr__(self) -> str:
        type_name = self.header.frame_type.name if self.header.frame_type else f"UNKNOWN_{self.header.frame_type_code}"
        return f"{self.__class__.__name__}({type_name}, size={self.header.frame_size}, parsed={self.parsed})"
