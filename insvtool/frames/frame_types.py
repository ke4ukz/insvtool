"""Frame type enumeration for INSV metadata."""

from enum import IntEnum
from typing import Optional


class FrameType(IntEnum):
    """Enumeration of INSV frame types."""
    RAW = -1
    INDEX = 0
    INFO = 1
    THUMBNAIL = 2
    GYRO = 3
    EXPOSURE = 4
    THUMBNAIL_EXT = 5
    TIMELAPSE = 6
    GPS = 7
    STAR_NUM = 8
    THREE_A_IN_TIMESTAMP = 9
    ANCHORS = 10
    THREE_A_SIMULATION = 11
    EXPOSURE_SECONDARY = 12
    MAGNETIC = 13
    EULER = 14
    GYRO_SECONDARY = 15
    SPEED = 16
    TBOX = 17
    EDITOR = 18
    HEARTRATE = 19
    FORWARD_DIRECTION = 20
    UPVIEW = 21
    SHELL_RECOGNITION_DATA = 22
    POS = 23
    TIMELAPSE_QUAT = 24

    @classmethod
    def from_code(cls, code: int) -> Optional['FrameType']:
        """Get FrameType from code, returns None if not found."""
        for frame_type in cls:
            if frame_type.value == code:
                return frame_type
        return None

    @classmethod
    def from_name(cls, name: str) -> Optional['FrameType']:
        """Get FrameType from name (case-insensitive), returns None if not found."""
        name_upper = name.upper()
        for frame_type in cls:
            if frame_type.name == name_upper:
                return frame_type
        return None


# Default frame types that are parsed automatically
DEFAULT_PARSED_TYPES = {
    FrameType.INDEX,
    FrameType.INFO,
    FrameType.GYRO,
    FrameType.EXPOSURE,
    FrameType.TIMELAPSE,
    FrameType.GPS,
}

# Additional frame types that can be included via --include
OPTIONAL_PARSED_TYPES = {
    FrameType.MAGNETIC,
    FrameType.EULER,
    FrameType.GYRO_SECONDARY,
    FrameType.SPEED,
    FrameType.HEARTRATE,
    FrameType.EXPOSURE_SECONDARY,
    FrameType.POS,
}
