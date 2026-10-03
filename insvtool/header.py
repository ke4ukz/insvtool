"""INSV file header parsing."""

import struct
from typing import BinaryIO, Optional


SIGNATURE = b"8db42d694ccc418790edff439fe026bf"
HEADER_SIZE = 72


class InsvHeader:
    """INSV metadata header located at the end of the file."""

    def __init__(self, unknown_buf: bytes, version: int, metadata_size: int, metadata_pos: int):
        self.unknown_buf = unknown_buf
        self.version = version
        self.metadata_size = metadata_size
        self.metadata_pos = metadata_pos

    @classmethod
    def read(cls, file: BinaryIO, file_size: int) -> Optional['InsvHeader']:
        """
        Read metadata header from the file.

        Args:
            file: Open file in binary mode
            file_size: Total size of the file

        Returns:
            InsvHeader if valid header found, None otherwise
        """
        if file_size < HEADER_SIZE:
            return None

        file.seek(file_size - HEADER_SIZE)
        header_data = file.read(HEADER_SIZE)

        if len(header_data) != HEADER_SIZE:
            return None

        # Parse header (little-endian)
        # 32 bytes unknown, 4 bytes metadata_size, 4 bytes version, 32 bytes signature
        unknown_buf = header_data[0:32]
        metadata_size = struct.unpack('<I', header_data[32:36])[0]
        version = struct.unpack('<I', header_data[36:40])[0]
        signature = header_data[40:72]

        if signature != SIGNATURE:
            return None  # No valid header

        if version != 3:
            raise ValueError(f"Unsupported file version {version}")

        metadata_pos = file_size - metadata_size

        return cls(unknown_buf, version, metadata_size, metadata_pos)

    def to_dict(self) -> dict:
        """Convert header to dictionary for JSON serialization."""
        return {
            'version': self.version,
            'metaDataSize': self.metadata_size,
            'metaDataPos': self.metadata_pos,
        }
