"""Write standard QuickTime GPS metadata with Python or ExifTool."""

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from .header import InsvHeader
from .quicktime import write_location, read_location


def trailer_digest(path):
    """Hash the proprietary trailer without reading the media into memory."""
    with open(path, 'rb') as file:
        file.seek(0, os.SEEK_END)
        size = file.tell()
        header = InsvHeader.read(file, size)
        if header is None or not (0 <= header.metadata_pos < size):
            raise ValueError('No valid INSV trailer found')
        file.seek(header.metadata_pos)
        digest = hashlib.sha256()
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
        return digest.digest()


def run_exiftool(executable, *args):
    result = subprocess.run([executable, '-config', '', *args],
                            capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or 'ExifTool failed')
    return result.stdout


def set_location(filename, location, executable=None, output=None, overwrite=False):
    """Verify an edited copy before publishing it to the selected destination."""
    path = Path(os.path.abspath(filename))
    if path.is_symlink():
        raise ValueError('Location writes do not support symbolic links')
    destination = Path(os.path.abspath(output)) if output is not None else path
    if destination.is_symlink():
        raise ValueError('Location outputs do not support symbolic links')
    if destination.exists() and not destination.is_file():
        raise ValueError('Location output must be a regular file')
    in_place = destination == path
    if destination.exists() and not in_place and not overwrite:
        raise ValueError('Output file already exists')
    destination_stat = destination.stat() if destination.exists() else None
    original_stat = path.stat()
    original_trailer = trailer_digest(path)
    # ExifTool supports the container but refuses writing the INSV extension.
    with tempfile.TemporaryDirectory(prefix='.insvtool-', dir=destination.parent) as directory:
        edited = Path(directory) / 'video.mp4'
        if executable is None:
            write_location(path, edited, location)
            if trailer_digest(edited) != original_trailer:
                raise ValueError('Writer changed the Insta360 trailer; original file was not modified')
            expected = f"{location['latitude']:+012.8f}{location['longitude']:+013.8f}/"
            if read_location(edited) != expected:
                raise ValueError('Written GPS coordinates failed verification; original file was not modified')
        else:
            shutil.copy2(path, edited)
            run_exiftool(executable, '-overwrite_original',
                         f"-Keys:GPSCoordinates={location['latitude']}, {location['longitude']}",
                         str(edited))
            if trailer_digest(edited) != original_trailer:
                raise ValueError('Writer changed the Insta360 trailer; original file was not modified')
            values = json.loads(run_exiftool(executable, '-j', '-n', '-Keys:GPSCoordinates', str(edited)))
            coordinates = values[0].get('GPSCoordinates', '').split()
            if len(coordinates) < 2 or not all(
                    math.isclose(float(actual), location[key], abs_tol=1e-6, rel_tol=0)
                    for actual, key in zip(coordinates, ('latitude', 'longitude'))):
                raise ValueError('Written GPS coordinates failed verification; original file was not modified')
        current_stat = path.stat()
        if (current_stat.st_ino, current_stat.st_size, current_stat.st_mtime_ns) != (
                original_stat.st_ino, original_stat.st_size, original_stat.st_mtime_ns):
            raise ValueError('Input file changed during processing; refusing to replace it')
        shutil.copystat(path, edited)
        # Preserve permissions and access time, but reflect the metadata edit.
        os.utime(edited, ns=(original_stat.st_atime_ns, time.time_ns()))
        if in_place:
            os.replace(edited, destination)
        elif destination_stat is None:
            # Atomic creation without silently overwriting a file that appeared
            # after confirmation or while the video was being processed.
            os.link(edited, destination)
        else:
            current_destination = destination.stat()
            if (current_destination.st_ino, current_destination.st_size, current_destination.st_mtime_ns) != (
                    destination_stat.st_ino, destination_stat.st_size, destination_stat.st_mtime_ns):
                raise ValueError('Output file changed during processing; refusing to overwrite it')
            os.replace(edited, destination)
