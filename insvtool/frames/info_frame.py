"""Info frame class for INSV metadata (protobuf-encoded)."""

from typing import TYPE_CHECKING

from .frame import Frame
from .frame_header import FrameHeader

if TYPE_CHECKING:
    from ..metadata import InsvMetadata


class InfoFrame(Frame):
    """Info frame containing protobuf-encoded extra metadata."""

    def __init__(self, header: FrameHeader, payload: bytes):
        super().__init__(header, payload)
        self.extra_metadata = None
        self._gyro_data_size = 0

    def _parse_internal(self, metadata: 'InsvMetadata') -> bool:
        """Parse protobuf data from payload."""
        # Version 1 = ProtoBuf serializer, other versions use JSON (not supported)
        if self.header.frame_version != 1:
            raise ValueError(f"Unsupported InfoFrame version {self.header.frame_version}")

        from ..proto import extra_metadata_pb2

        self.extra_metadata = extra_metadata_pb2.ExtraMetadata()
        self.extra_metadata.ParseFromString(self.payload)

        # Store gyro data size for GyroFrame parsing
        if self.extra_metadata.HasField('Gyro'):
            self._gyro_data_size = len(self.extra_metadata.Gyro)

        return True

    def get_gyro_record_size(self) -> int:
        """Get the size of gyro records from embedded gyro data."""
        return self._gyro_data_size

    def to_dict(self) -> dict:
        """Convert frame to dictionary for JSON serialization."""
        result = super().to_dict()
        if self.parsed and self.extra_metadata:
            from google.protobuf.json_format import MessageToDict
            result['extraMetadata'] = MessageToDict(
                self.extra_metadata,
                preserving_proto_field_name=True
            )
        return result
