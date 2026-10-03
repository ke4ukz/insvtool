"""POS (drone position/telemetry) record class."""

import struct
import math

from .base import TimestampedRecord


class PosRecord(TimestampedRecord):
    """
    POS record (44 bytes): drone position and velocity telemetry.

    Found in drone recordings (e.g., Antigravity A1).
    Uses 4-byte millisecond timestamps (not 8-byte like other records).

    Fields (confirmed):
    - timestamp: milliseconds
    - velocity_h, velocity_v: velocity components (m/s)
    - agl: above ground level in meters (-1.0 = N/A)

    Fields (partially understood):
    - x_pos, y_pos, z_pos: local position coordinates (units unclear, NOT distance from home)
    - float3-5: possibly accelerometer or other sensor data
    - float8: unknown
    """

    SIZE = 44  # 4 byte timestamp + 10 floats (40 bytes)

    def __init__(self, timestamp: int, x_pos: float, y_pos: float, z_pos: float,
                 float3: float, float4: float, float5: float,
                 velocity_h: float, velocity_v: float, float8: float,
                 agl: float):
        super().__init__(timestamp)
        self.x_pos = x_pos
        self.y_pos = y_pos
        self.z_pos = z_pos
        self.float3 = float3
        self.float4 = float4
        self.float5 = float5
        self.velocity_h = velocity_h  # Horizontal velocity component (m/s)
        self.velocity_v = velocity_v  # Vertical velocity / climb rate (m/s)
        self.float8 = float8
        self.agl = agl  # Above ground level (meters), -1.0 = N/A

    @classmethod
    def parse(cls, data: bytes, offset: int = 0) -> 'PosRecord':
        """Parse a POS record from bytes."""
        # 4-byte timestamp (milliseconds)
        timestamp = struct.unpack_from('<I', data, offset)[0]

        # 10 floats
        floats = struct.unpack_from('<10f', data, offset + 4)

        return cls(
            timestamp=timestamp,
            x_pos=floats[0],
            y_pos=floats[1],
            z_pos=floats[2],
            float3=floats[3],
            float4=floats[4],
            float5=floats[5],
            velocity_h=floats[6],
            velocity_v=floats[7],
            float8=floats[8],
            agl=floats[9],
        )

    @property
    def speed(self) -> float:
        """Calculate total speed magnitude (m/s)."""
        return math.sqrt(self.velocity_h ** 2 + self.velocity_v ** 2)

    @property
    def agl_valid(self) -> bool:
        """Check if AGL reading is valid (not N/A)."""
        return self.agl > 0

    def to_dict(self) -> dict:
        """Convert record to dictionary for JSON serialization."""
        result = {
            'timestamp': self.timestamp,
            'xPos': self.x_pos,
            'yPos': self.y_pos,
            'zPos': self.z_pos,
            'velocityH': self.velocity_h,
            'velocityV': self.velocity_v,
            'speed': self.speed,
        }

        # Only include AGL if valid
        if self.agl_valid:
            result['agl'] = self.agl

        return result
