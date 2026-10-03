"""JSON serialization for INSV metadata."""

import json
from typing import Any

from .metadata import InsvMetadata
from .frames.frame import Frame


def dump_metadata(metadata: InsvMetadata) -> str:
    """
    Dump INSV metadata to JSON string.

    Args:
        metadata: InsvMetadata object

    Returns:
        JSON string
    """
    return json.dumps(metadata.to_dict(), indent=2)


def dump_frame(frame: Frame) -> str:
    """
    Dump a single frame to JSON string.

    Args:
        frame: Frame object

    Returns:
        JSON string
    """
    return json.dumps(frame.to_dict(), indent=2)
