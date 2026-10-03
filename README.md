# insvtool

A Python command-line tool for inspecting Insta360 INSV video metadata, exporting JSON, and extracting locations with map links.

This is a Python port of the `dump-meta` command from [insvtools](https://github.com/alex-plekhanov/insvtools), a Java-based toolkit for working with Insta360 video files. The Python version provides the same metadata extraction functionality with fewer dependencies.

## Features

- Extracts metadata from Insta360 INSV video files
- Outputs human-readable JSON format
- Parses common frame types: INFO, GYRO, GPS, EXPOSURE, TIMELAPSE
- Optional parsing for additional frame types (MAGNETIC, EULER, etc.)
- Requires `protobuf`; optional ExifTool backend for writing standard location metadata

## Installation

### Requirements

- Python 3.7+
- `protobuf` package

### Setup

```bash
# Install the protobuf dependency
pip install protobuf

# Clone the repository, then run insvtool.py from its directory
```

## Usage

```bash
# Basic usage - outputs to video.insv.meta.json
python insvtool.py video.insv

# Specify output file
python insvtool.py video.insv -o output.json

# Print JSON to stdout (also works with --frame-type)
python insvtool.py video.insv -o -

# Print GPS coordinates, timestamp, place name, and an OpenStreetMap pin link
python insvtool.py video.insv --location
python insvtool.py -l *.insv
python insvtool.py -l 1:30:00.000 video.insv
python insvtool.py -l -0 video.insv
python insvtool.py -l -60.5 video.insv

# Dump only a specific frame type (by numeric code)
python insvtool.py video.insv --frame-type 3

# Include additional frame types for parsing
python insvtool.py video.insv --include MAGNETIC,EULER
python insvtool.py video.insv --include MAGNETIC --include EULER

# Scan a file to see what frame types it contains (no dump)
python insvtool.py video.insv --scan

# Scan multiple files
python insvtool.py --scan *.insv

# List all known frame types
python insvtool.py --list-types
```

### Command-line Options

| Option | Description |
|--------|-------------|
| `input` | Input INSV file(s) (multiple files supported with `--scan` or `--location`) |
| `-o, --output` | Output JSON file (`-` for stdout), or destination video when writing; ignored for read-only `-l` |
| `-l, --location [TIME]` | Print locations nearest TIME, or select the location to write with `--set-exif-location` (default TIME: 0) |
| `--location-search-range SECONDS` | Search within ±SECONDS of TIME (default: 60); 0 searches all GPS records for the nearest valid fix |
| `--set-exif-location` | Modify input files to write the selected location into QuickTime GPS metadata (defaults to `-l 0`) |
| `--exiftool [PATH]` | Use the external ExifTool writer; without PATH, resolve `exiftool` on PATH |
| `-y, --yes` | Skip the backup warning confirmation for `--set-exif-location` |
| `--frame-type CODE` | Dump only the specified frame type by numeric code |
| `--include TYPES` | Include additional frame types for parsing (comma-separated); GPS is already parsed by default |
| `--scan` | Scan file(s) and show frame types with counts (no dump) |
| `--list-types` | List all known frame types and exit |

## Write standard location metadata

```bash
python insvtool.py --set-exif-location video.insv
python insvtool.py --set-exif-location -l -0 video.insv
python insvtool.py --set-exif-location video.insv -o located.insv
python insvtool.py --set-exif-location -l 90.5 -y *.insv

# Optional alternative backend
python insvtool.py --set-exif-location --exiftool video.insv
python insvtool.py --set-exif-location --exiftool /path/to/exiftool video.insv
```

The default writer edits QuickTime metadata directly in Python, with no external
binary dependency. Location metadata uses the QuickTime layout recognized by
Apple AVFoundation; updating a file also repairs the ISO-style layout produced
by earlier versions of this writer. It supports non-fragmented containers with one movie metadata
box, preserving other metadata and media offsets. Fragmented, malformed, or
unsupported layouts fail without replacing the file. Compatibility with future
INSV versions or every media application is not guaranteed.

`--exiftool` uses the environment's `exiftool` executable instead. Supply a path
as an optional argument, or use `--exiftool=/path/to/exiftool` to make the argument
unambiguous. ExifTool is needed only for this backend (macOS: `brew install exiftool`).
Both backends retain the backup warning and support `-y`.

Despite the command name, videos use QuickTime `Keys:GPSCoordinates`
(`com.apple.quicktime.location.ISO6709`), rather than photo EXIF GPS tags.
The same time selection and ±60-second limit as `-l` apply. Without `-l`, the
command uses the start location. Standard location visibility depends on the
inspector's support for that tag.

Without `-o`, this modifies the input files. Keep a backup: the command asks for
`y` once before processing the batch. With `-o new.insv`, it writes a separate
video and skips the modification confirmation. If the destination already
exists, it asks `Overwrite? [y/n]`. `-y` skips either confirmation. Any other
response or EOF cancels. Naming the input itself as the output still requires
the modification confirmation. Writing to `-o` supports one input file and
requires a filename; `-o -` is rejected in this mode. No automatic backup is retained. The edited file gets a current filesystem
modification time; embedded recording dates remain unchanged. An edited temporary copy is verified
for matching coordinates and a byte-identical Insta360 trailer before replacing
the selected destination. Temporary disk space is required for a full edited copy (and another rewrite
when using ExifTool).
Symbolic-link inputs are rejected. Finder tags and comments are separate metadata;
their preservation by the replacement has not been verified.

Location results use the readable report described below, with a `Written` line
on successful writes. Failures show `Error`, continue to the next file, and cause
exit status 1. Prompts and status messages go to stderr. Reports always go to
stdout; in write mode, `-o` selects the video destination.

macOS Finder and Photos recognize the location when a compatible file has an
`.mp4` extension. They do not use it for `.insv`, which relies on Insta360's
preview handler; Photos does not import INSV directly. A `.mp4` copy still has
unstitched camera streams and may show a fisheye image.

## Location reports

`--location [TIME]` selects the nearest valid active GPS fix within 60 seconds
before or after the requested time. TIME accepts decimal seconds or `h:mm:ss.fff`
(fractional seconds optional), defaulting to `0:00:00.000`. Positive times count
from the start; a leading minus counts backward from the end, including `-0`
for the end itself. The same offset applies separately to each input file.
Equal-distance fixes use the first encountered record. Times outside the video
are errors. `--location-search-range SECONDS` changes the search radius;
`0` removes the limit and selects the nearest valid fix anywhere in the GPS
records, including records whose timestamps fall outside the current segment.
This can select stale data from earlier recording segments.

The search skips void fixes, invalid hemisphere markers, non-finite coordinates,
and coordinates outside geographic bounds. Active status indicates a valid fix;
the format has no decoded accuracy score. South and west coordinates are returned
as negative decimal degrees.

Timing uses GPS Unix seconds plus milliseconds and the INFO `FirstGpsTimestamp`
anchor (milliseconds). End-relative lookups also require INFO `TotalTime` (whole
seconds, so the end reference has that precision). If the anchor is absent, only
an untimed/default start lookup is supported, using the first GPS timestamp.
Timed lookups fail rather than estimating timing from file dates. TimeShift and
timelapse playback may not align with the GPS recording clock.

Location output is plain text, with one block per file in input order. Each block
is printed and flushed as soon as that file finishes; attribution appears once
at the end. It always
goes to stdout; `-o` is ignored for read-only `-l`. Each block contains the absolute
path, the actual selected GPS record's video offset, its full GPS timestamp in
UTC, exact decimal-degree coordinates on one line, an approximate place name,
and an OpenStreetMap pin link. The video offset is shown as unknown if timing
metadata is missing. GPS date/time reflects the timestamp encoded in the record;
no camera-specific GPS/UTC clock correction is applied.

Example (place name is illustrative):

```text
/full/path/video.insv
  Video time: 0:00:10.125
  GPS date/time: 2026-01-18T21:30:05.125Z
  Coordinates: 29.67829760, -84.87257690
  Location: Eastpoint, Florida, United States
  Map: https://www.openstreetmap.org/?mlat=29.6782976&mlon=-84.8725769#map=16/29.6782976/-84.8725769

Location names and maps: © OpenStreetMap contributors (ODbL), https://www.openstreetmap.org/copyright
```

Files without a valid fix show an error block. A failed place-name lookup still
shows the coordinates, timestamps, and map link, with the name unavailable.
Processing continues and exit status is 1 if any file or name lookup failed.
`-l` cannot be combined with `--scan`, `--list-types`, or `--frame-type`.
Full metadata and individual-frame dumps retain their original JSON format and
`-o` behavior. Warnings, errors, and confirmations go to stderr.

### Place names and caching

Location reports request approximate named places and settlements from Nominatim. Coordinates
are rounded to three decimal places for both the request and cache key (roughly
100-meter cells); reported coordinates and map pins retain their exact values.
Successful names are cached in `~/.insvtool_location_cache.db` using Python's
built-in SQLite support, with no expiration. Cached locations need no network
request. The cache key includes the provider URL, language, detail level, layers, and name
format version, so older county-level results do not hide more detailed lookups.

Requests use `zoom=17` (street level, below building/address detail) and include
address, points of interest, and natural features. The formatter prefers named
parks, islands, and landmarks, then neighbourhoods and settlements, then county,
state, or country. House numbers, roads, and full street addresses are excluded.
Nominatim returns one nearby suitable object, so a park or island name is not
guaranteed and the rounded point can occasionally select a neighbouring place.

Uncached requests are serialized and spaced at least 1.05 seconds apart by start
time, including across local processes sharing the cache. Coordinate extraction
and request time count toward that interval. Requests use an identifying
`insvtool` User-Agent and a 10-second timeout. Attribution appears once per report
and in help. The lookup sends rounded coordinates to the service; do not use it
for confidential locations.

Use this feature for occasional manual runs. The public service's
[Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/)
discourages large batches and restricts regularly scheduled or day-long scripts
to four requests per minute. Do not use the default endpoint for those workloads
or distributed runs. The application's aggregate traffic must also stay within
the service's limits.

Set `INSVTOOL_NOMINATIM_URL` to another compatible reverse endpoint to change
providers without a software update. Set `INSVTOOL_LOCATION_CACHE` to select a
different cache database path. Cache access or network failures leave the GPS
report usable and appear as place-name lookup failures.

## Frame Types

### Default Parsed Frames
| Code | Name | Description |
|------|------|-------------|
| 0 | INDEX | Frame index/offset table (internal) |
| 1 | INFO | Protobuf-encoded camera/file metadata |
| 3 | GYRO | Gyroscope sensor data |
| 4 | EXPOSURE | Camera exposure/shutter speed data |
| 6 | TIMELAPSE | Timelapse timestamp mapping |
| 7 | GPS | GPS location data |

### Optional Frames (use `--include`)
| Code | Name | Description |
|------|------|-------------|
| 12 | EXPOSURE_SECONDARY | Secondary exposure data |
| 13 | MAGNETIC | Magnetometer data |
| 14 | EULER | Orientation quaternions |
| 15 | GYRO_SECONDARY | Secondary gyroscope data |
| 16 | SPEED | Speed data |
| 19 | HEARTRATE | Heart rate monitor data |
| 23 | POS | Drone position/telemetry (see below) |

## Output Format

The JSON output structure matches the original Java tool:

```json
{
  "header": {
    "version": 3,
    "metaDataSize": 11001446,
    "metaDataPos": 272035488
  },
  "frames": [
    {
      "header": {
        "frameType": "INFO",
        "frameVersion": 1,
        "frameSize": 2954,
        "framePos": 283033646
      },
      "parsed": true,
      "extraMetadata": {
        "SerialNumber": "...",
        "CameraType": "Insta360 X4",
        "FwVersion": "v1.7.19_build1",
        "CreationTime": "20250615170133",
        ...
      }
    },
    {
      "header": {
        "frameType": "EXPOSURE",
        ...
      },
      "parsed": true,
      "records": [
        {"timestamp": 159610801, "shutterSpeed": 0.000815},
        ...
      ]
    }
  ]
}
```

## Drone Telemetry (POS Frame)

Videos recorded on drones (e.g., Antigravity A1) include a POS frame with flight telemetry data. Use `--include POS` to parse this data.

```bash
python insvtool.py drone_video.insv --include POS
```

### POS Record Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | int | Timestamp in milliseconds |
| `xPos` | float | Local X position (units unclear) |
| `yPos` | float | Local Y position (units unclear) |
| `zPos` | float | Local Z position (units unclear) |
| `velocityH` | float | Horizontal velocity component (m/s) |
| `velocityV` | float | Vertical velocity / climb rate (m/s) |
| `speed` | float | Total speed magnitude (m/s) |
| `agl` | float | Above Ground Level in meters (omitted if N/A) |

**Note:** The `xPos`/`yPos`/`zPos` fields are local position coordinates whose exact meaning is not fully understood. They do NOT represent distance from home. To calculate total distance traveled, integrate the `speed` field over time.

### Example Output

```json
{
  "header": {"frameType": "POS", ...},
  "parsed": true,
  "records": [
    {
      "timestamp": 918895,
      "xPos": -0.0287,
      "yPos": -0.0193,
      "zPos": 1.8612,
      "velocityH": 0.0095,
      "velocityV": -0.0249,
      "speed": 0.0267,
      "agl": 4.65
    },
    ...
  ]
}
```

### Drone-Specific Frame Types

Drone recordings also include additional frame types that are not yet fully decoded:

| Code | Status | Notes |
|------|--------|-------|
| 32 | Unknown | Large frame, likely contains extended telemetry |
| 33 | Unknown | 33-byte records at 50Hz, possibly accelerometer data |
| 37 | Unknown | 36-byte records at 50Hz, velocity/orientation data |
| 38 | Unknown | Small frame, possibly configuration or summary |

The POS frame provides the most useful telemetry (position, velocity, AGL) for most applications.

### Reverse Engineering Status

**Confirmed fields:**
- `agl` (Float[9]): Above Ground Level in meters, -1.0 = N/A. Verified against video overlay.
- `velocityV` (Float[7]): Vertical velocity component in m/s. Correlates with overlay "D" (depth/vertical delta).
- `velocityH` (Float[6]): Horizontal velocity component in m/s.

**Partially understood:**
- `xPos`, `yPos`, `zPos` (Float[0-2]): Local position coordinates. NOT distance from home. Units and reference frame unclear. Values fluctuate rather than accumulate.
- Float[3-5]: Large values that change over time, possibly world coordinates or sensor data.
- Float[8]: Unknown, small values.

**Future work:** Controlled test flights (see [FLIGHT_TEST_PLAN.md](FLIGHT_TEST_PLAN.md)) would help decode the remaining fields.

## Notes

- **GYRO frame parsing**: The GYRO frame can only be parsed if the INFO frame contains a non-empty `Gyro` field (used to determine record size). This is the same behavior as the original Java tool.
- **INSV file format**: Metadata is stored at the end of the file and read backwards. The tool handles both indexed and non-indexed metadata formats.
- **Protobuf**: The `extra_metadata_pb2.py` file is pre-compiled and included, so you don't need the `protoc` compiler installed.

## Project Structure

```
<project directory>/
├── insvtool.py                    # Standalone entry point
├── extra_metadata.proto            # Proto source (for reference)
├── README.md
└── insvtool/                      # Package
    ├── __init__.py
    ├── header.py                   # INSV file header parsing
    ├── metadata.py                 # Main orchestration
    ├── dump.py                     # JSON serialization
    ├── location.py                 # Timed GPS selection
    ├── location_output.py          # Readable reports
    ├── geocode.py                  # Cached city names
    ├── quicktime.py                # Direct metadata editing
    ├── set_location.py             # Verified video writes
    ├── frames/                     # Frame type implementations
    │   ├── frame_types.py
    │   ├── frame_header.py
    │   ├── frame.py
    │   ├── index_frame.py
    │   ├── info_frame.py
    │   ├── timestamped.py
    │   ├── gyro_frame.py
    │   ├── gps_frame.py
    │   ├── exposure_frame.py
    │   ├── timelapse_frame.py
    │   └── pos_frame.py            # Drone position/telemetry
    ├── records/                    # Record type implementations
    │   ├── base.py
    │   ├── gyro.py
    │   ├── gps.py
    │   ├── exposure.py
    │   ├── timelapse.py
    │   └── pos.py                  # Drone position records
    └── proto/
        └── extra_metadata_pb2.py   # Compiled protobuf
```

## License

This project is a derivative work based on [insvtools](https://github.com/alex-plekhanov/insvtools) by Alex Plekhanov, which is licensed under the Apache License 2.0.

This Python port is also licensed under the Apache License 2.0.

## Third-Party Licenses

### insvtools
- **Source**: https://github.com/alex-plekhanov/insvtools
- **License**: Apache License 2.0
- **Copyright**: Alex Plekhanov

### Protocol Buffers
- **Source**: https://github.com/protocolbuffers/protobuf
- **License**: BSD 3-Clause License
- **Copyright**: Google LLC

The `extra_metadata.proto` file format is derived from reverse-engineering the Insta360 INSV file format by the insvtools project.

## See Also

- [insvtools](https://github.com/alex-plekhanov/insvtools) - The original Java toolkit with additional features (video cutting, metadata manipulation, etc.)
- [Protocol Buffers](https://github.com/protocolbuffers/protobuf) - Google's data serialization library
