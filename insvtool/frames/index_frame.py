"""Index frame class for INSV metadata."""

import struct
from typing import List, Optional, TYPE_CHECKING

from .frame import Frame
from .frame_header import FrameHeader

if TYPE_CHECKING:
    from ..metadata import InsvMetadata


INDEX_ENTRY_SIZE = 10  # type(1) + version(1) + size(4) + offset(4)


class IndexFrame(Frame):
    """Index frame containing a directory of other frames."""

    def __init__(self, header: FrameHeader, payload: bytes):
        super().__init__(header, payload)
        self.frames_index: List[Optional[FrameHeader]] = []

    def _parse_internal(self, metadata: 'InsvMetadata') -> bool:
        """Parse index entries from payload."""
        if len(self.payload) % INDEX_ENTRY_SIZE != 0:
            raise ValueError(f"Unexpected INDEX frame size: {len(self.payload)}")

        metadata_pos = metadata.header.metadata_pos

        offset = 0
        while offset < len(self.payload):
            entry_data = self.payload[offset:offset + INDEX_ENTRY_SIZE]
            frame_header = FrameHeader.from_index_entry(entry_data, metadata_pos)
            self.frames_index.append(frame_header)
            offset += INDEX_ENTRY_SIZE

        return True

    def to_dict(self) -> dict:
        """Convert frame to dictionary for JSON serialization."""
        result = super().to_dict()
        if self.parsed:
            result['framesIndex'] = [
                h.to_dict() if h else None
                for h in self.frames_index
            ]
        return result
