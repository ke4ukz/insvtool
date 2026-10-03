"""INSV metadata reading and parsing."""

import os
from typing import BinaryIO, List, Optional, Set

from .header import InsvHeader, HEADER_SIZE
from .frames.frame import Frame
from .frames.frame_header import FrameHeader, FRAME_HEADER_SIZE
from .frames.frame_types import FrameType, DEFAULT_PARSED_TYPES
from .frames.index_frame import IndexFrame


class InsvMetadata:
    """Container for INSV file metadata."""

    def __init__(self, header: InsvHeader, frames: List[Frame]):
        self.header = header
        self.frames = frames

    @classmethod
    def read(cls, file: BinaryIO) -> Optional['InsvMetadata']:
        """
        Read INSV metadata from a file.

        Args:
            file: Open file in binary mode

        Returns:
            InsvMetadata if valid metadata found, None otherwise
        """
        # Get file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()

        # Read header
        header = InsvHeader.read(file, file_size)
        if header is None:
            return None

        frames: List[Frame] = []
        metadata = cls(header, frames)

        # Read frames backward from end of file
        cur_pos = file_size - HEADER_SIZE

        while cur_pos > header.metadata_pos:
            frame_header = FrameHeader.read_backward(file, cur_pos)
            frame = Frame.read(file, frame_header)
            frames.append(frame)

            # If we found an INDEX frame, use it to read remaining frames
            if frame_header.frame_type == FrameType.INDEX:
                frame.parse(metadata)
                frames.extend(cls._read_indexed_frames(file, frame, metadata))
                break

            cur_pos = cur_pos - frame_header.frame_size - FRAME_HEADER_SIZE

        # Check if there's raw data at the beginning of metadata
        if frames:
            last_frame = frames[-1]
            if last_frame.header.frame_pos > header.metadata_pos:
                raw_frame = Frame.read_raw(file, header.metadata_pos, last_frame.header.frame_pos)
                frames.append(raw_frame)

        # Reverse frames (we read last-to-first, store first-to-last)
        frames.reverse()

        return metadata

    @classmethod
    def _read_indexed_frames(cls, file: BinaryIO, index_frame: IndexFrame,
                              metadata: 'InsvMetadata') -> List[Frame]:
        """Read frames using the index frame for direct access."""
        frames: List[Frame] = []

        for frame_header in index_frame.frames_index:
            if frame_header is None:
                continue

            frame = Frame.read(file, frame_header)
            frames.append(frame)

        # Sort by position (descending) to match the backward reading order
        frames.sort(key=lambda f: -f.header.frame_pos)

        result: List[Frame] = []
        prev_pos = index_frame.header.frame_pos

        for frame in frames:
            frame_end_pos = frame.header.frame_pos + frame.header.frame_size + FRAME_HEADER_SIZE

            # Check for raw data between frames
            if frame_end_pos < prev_pos:
                raw_frame = Frame.read_raw(file, frame_end_pos, prev_pos)
                result.append(raw_frame)

            result.append(frame)
            prev_pos = frame.header.frame_pos

        return result

    def parse(self, include_types: Optional[Set[FrameType]] = None) -> None:
        """
        Parse all frames in the metadata.

        Args:
            include_types: Additional frame types to parse beyond defaults
        """
        # Determine which types to parse
        types_to_parse = set(DEFAULT_PARSED_TYPES)
        if include_types:
            types_to_parse.update(include_types)

        # Find INFO frame first (needed for GYRO parsing)
        info_frame = self.find_frame(FrameType.INFO)
        if info_frame is not None:
            info_frame.parse(self)

        # Parse other frames
        for frame in self.frames:
            if frame is info_frame:
                continue  # Already parsed

            frame_type = frame.header.frame_type
            if frame_type in types_to_parse:
                frame.parse(self)

    def find_frame(self, frame_type: FrameType) -> Optional[Frame]:
        """Find a frame by type."""
        for frame in self.frames:
            if frame.header.frame_type == frame_type:
                return frame
        return None

    def find_frame_by_code(self, frame_type_code: int) -> Optional[Frame]:
        """Find a frame by type code."""
        for frame in self.frames:
            if frame.header.frame_type_code == frame_type_code:
                return frame
        return None

    def to_dict(self) -> dict:
        """Convert metadata to dictionary for JSON serialization."""
        return {
            'header': self.header.to_dict(),
            'frames': [f.to_dict() for f in self.frames],
        }
