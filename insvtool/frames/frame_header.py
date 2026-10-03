"""Frame header parsing for INSV metadata."""

import struct
from typing import BinaryIO, Optional

from .frame_types import FrameType


FRAME_HEADER_SIZE = 6


class FrameHeader:
    """Header for an individual frame within INSV metadata."""

    def __init__(self, frame_type_code: int, frame_version: int, frame_size: int, frame_pos: int):
        self.frame_type_code = frame_type_code
        self.frame_type = FrameType.from_code(frame_type_code)
        self.frame_version = frame_version
        self.frame_size = frame_size
        self.frame_pos = frame_pos

    @classmethod
    def read_backward(cls, file: BinaryIO, cur_pos: int) -> 'FrameHeader':
        """
        Read frame header from the file (reading backward from current position).

        The frame header is located at the end of the frame data, so we read
        backward from cur_pos.

        Args:
            file: Open file in binary mode
            cur_pos: Current position (end of frame including header)

        Returns:
            FrameHeader with frame information
        """
        # Header is at the end of the frame, read 6 bytes before cur_pos
        file.seek(cur_pos - FRAME_HEADER_SIZE)
        header_data = file.read(FRAME_HEADER_SIZE)

        # Parse: version (1 byte), type (1 byte), size (4 bytes little-endian)
        frame_version = header_data[0]
        frame_type_code = header_data[1]
        frame_size = struct.unpack('<I', header_data[2:6])[0]

        # Frame data position is before the header
        frame_pos = cur_pos - frame_size - FRAME_HEADER_SIZE

        return cls(frame_type_code, frame_version, frame_size, frame_pos)

    @classmethod
    def from_index_entry(cls, entry_data: bytes, metadata_pos: int) -> Optional['FrameHeader']:
        """
        Create FrameHeader from an index frame entry.

        Args:
            entry_data: 10 bytes of index entry data
            metadata_pos: Position where metadata starts in the file

        Returns:
            FrameHeader or None if entry is empty
        """
        # Index entry: type (1), version (1), size (4), offset (4)
        frame_type_code = entry_data[0]
        frame_version = entry_data[1]
        frame_size = struct.unpack('<I', entry_data[2:6])[0]
        offset = struct.unpack('<I', entry_data[6:10])[0]

        # Check for empty entry
        if frame_type_code == 0 and frame_version == 0 and frame_size == 0:
            return None

        frame_pos = metadata_pos + offset

        return cls(frame_type_code, frame_version, frame_size, frame_pos)

    def to_dict(self) -> dict:
        """Convert frame header to dictionary for JSON serialization."""
        return {
            'frameType': self.frame_type.name if self.frame_type else f"UNKNOWN_{self.frame_type_code}",
            'frameVersion': self.frame_version,
            'frameSize': self.frame_size,
            'framePos': self.frame_pos,
        }
