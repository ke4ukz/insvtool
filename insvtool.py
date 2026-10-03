#!/usr/bin/env python3
"""
insvtool

Standalone script to dump Insta360 INSV video file metadata to JSON format.
Replicates the functionality of the Java insvtools dump-meta command.

Usage:
    python insvtool.py video.insv
    python insvtool.py video.insv -o output.json
    python insvtool.py video.insv --frame-type 3
    python insvtool.py video.insv --include MAGNETIC,EULER
    python insvtool.py video.insv --scan
    python insvtool.py --scan *.insv
"""

import argparse
import os
import shutil
import sys
from typing import List, Optional, Set

# Add the package directory to the path for standalone execution
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from insvtool.metadata import InsvMetadata
from insvtool.dump import dump_metadata, dump_frame
from insvtool.frames.frame_types import FrameType, OPTIONAL_PARSED_TYPES
from insvtool.location import find_location, parse_location_time, TIME_PATTERN
from insvtool.set_location import set_location
from insvtool.geocode import Geocoder, ATTRIBUTION
from insvtool.location_output import format_location


def scan_frame_types(filename: str, metadata: 'InsvMetadata') -> None:
    """Scan and print frame types present in the metadata, with record counts."""
    from collections import defaultdict

    # Parse all frames to get record counts
    metadata.parse()

    # Count records per frame type (sum across all frames of same type)
    known_types: dict[FrameType, int] = defaultdict(int)
    unknown_types: dict[int, int] = defaultdict(int)

    for frame in metadata.frames:
        frame_type = frame.header.frame_type
        if frame_type == FrameType.RAW:
            continue  # Skip synthetic RAW frames

        # Get record count if frame has records, otherwise count as 1
        if hasattr(frame, 'records'):
            count = len(frame.records)
        else:
            count = 1

        if frame_type is not None:
            known_types[frame_type] += count
        else:
            unknown_types[frame.header.frame_type_code] += count

    # Print filename header
    print(f"{filename}:")

    # Print known types
    if known_types:
        for frame_type in sorted(known_types.keys(), key=lambda x: x.value):
            count = known_types[frame_type]
            print(f"  {frame_type.value:3d}: {frame_type.name:<24} {count:>12,}")

    # Print unknown types
    if unknown_types:
        print("  Unknown:")
        for code in sorted(unknown_types.keys()):
            count = unknown_types[code]
            print(f"  {code:3d}: {'???':<24} {count:>12,}")

    # Summary
    total_records = sum(known_types.values()) + sum(unknown_types.values())
    print(f"  Total: {total_records:,} records ({len(known_types)} known types, {len(unknown_types)} unknown)")
    print()


def parse_include_types(include_args: list) -> Set[FrameType]:
    """Parse --include arguments into a set of FrameTypes."""
    types = set()

    for arg in include_args:
        # Handle comma-separated values
        for name in arg.split(','):
            name = name.strip()
            if not name:
                continue

            frame_type = FrameType.from_name(name)
            if frame_type is None:
                print(f"Warning: Unknown frame type '{name}', ignoring", file=sys.stderr)
            else:
                types.add(frame_type)

    return types


def parse_args() -> argparse.Namespace:
    """Parse, normalize, and validate command-line arguments."""
    parser = argparse.ArgumentParser(
        description='insvtool: inspect Insta360 INSV video metadata',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s video.insv                      Dump to video.insv.meta.json
  %(prog)s video.insv -o output.json       Dump to output.json
  %(prog)s video.insv -o -                Dump JSON to stdout
  %(prog)s video.insv --location          Print first active GPS fix and map link
  %(prog)s video.insv --frame-type 3       Dump only GYRO frame
  %(prog)s video.insv --include MAGNETIC   Parse and include MAGNETIC frame
  %(prog)s video.insv --include MAGNETIC,EULER
  %(prog)s video.insv --scan               Show frame types in file
  %(prog)s --scan *.insv                   Scan multiple files
  %(prog)s -l *.insv                       Print locations near the start
  %(prog)s -l 1:30:00.000 video.insv       Location at 90 minutes
  %(prog)s -l -0 video.insv                Location near the end
  %(prog)s --set-exif-location video.insv   Write start location (asks for confirmation)
  %(prog)s --set-exif-location -l -0 -y video.insv
  %(prog)s -l -60.5 video.insv             Location 60.5 seconds before the end

Location names: © OpenStreetMap contributors (ODbL)
https://www.openstreetmap.org/copyright
Nominatim: occasional use only; cached lookups, at most 1 request/second.
https://operations.osmfoundation.org/policies/nominatim/

Available frame types for --include:
  MAGNETIC, EULER, GYRO_SECONDARY, SPEED, HEARTRATE, EXPOSURE_SECONDARY, POS
"""
    )
    parser.add_argument('input', nargs='*', help='Input INSV file(s)')
    parser.add_argument('-o', '--output',
                        help='Output JSON file (- for stdout), or destination video when writing; ignored with -l')
    parser.add_argument('-l', '--location', nargs='?', const='0', metavar='TIME',
                        help='Print location near TIME; negative times count from end (always stdout)')
    parser.add_argument('--set-exif-location', action='store_true',
                        help='Write the selected GPS fix into standard QuickTime location metadata')
    parser.add_argument('--exiftool', nargs='?', const='exiftool', metavar='PATH',
                        help='Use ExifTool instead of the Python writer (default binary: PATH lookup)')
    parser.add_argument('-y', '--yes', action='store_true',
                        help='Skip the confirmation for --set-exif-location')
    parser.add_argument('--frame-type', type=int, metavar='CODE',
                        help='Dump only the specified frame type (by numeric code)')
    parser.add_argument('--include', action='append', default=[], metavar='TYPES',
                        help='Include additional frame types for parsing (comma-separated)')
    parser.add_argument('--list-types', action='store_true',
                        help='List all known frame types and exit')
    parser.add_argument('--scan', action='store_true',
                        help='Scan file and show frame types present (no dump)')

    # Attach time values to the option so argparse accepts negative h:mm:ss
    # and does not consume a filename when -l has no time argument.
    argv = sys.argv[1:]
    normalized = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == '--':
            normalized.extend(argv[index:])
            break
        if arg in ('-l', '--location'):
            value = '0'
            if index + 1 < len(argv) and TIME_PATTERN.fullmatch(argv[index + 1]):
                index += 1
                value = argv[index]
            normalized.append('--location=' + value)
        elif arg == '--exiftool':
            value = 'exiftool'
            if index + 1 < len(argv):
                candidate = argv[index + 1]
                if not candidate.startswith('-') and not candidate.lower().endswith(('.insv', '.lrv')):
                    index += 1
                    value = candidate
            normalized.append('--exiftool=' + value)
        else:
            normalized.append(arg)
        index += 1
    args = parser.parse_intermixed_args(normalized)
    if args.location is not None:
        try:
            args.location = parse_location_time(args.location)
        except ValueError as e:
            parser.error(str(e))

    if args.set_exif_location and args.location is None:
        args.location = 0.0
    if args.exiftool is not None and not args.set_exif_location:
        parser.error('--exiftool requires --set-exif-location')
    if args.yes and not args.set_exif_location:
        parser.error('-y requires --set-exif-location')

    if args.location is not None and (args.scan or args.list_types or args.frame_type is not None):
        parser.error('--location cannot be combined with --scan, --list-types, or --frame-type')

    if not args.input and not args.list_types:
        parser.error("the following arguments are required: input")
    if args.set_exif_location:
        if args.output == '-':
            parser.error('--set-exif-location -o requires a video filename, not -')
        if args.output and len(args.input) != 1:
            parser.error('--set-exif-location with -o requires exactly one input file')
        if args.output and (os.path.islink(args.output) or
                            (os.path.lexists(args.output) and not os.path.isfile(args.output))):
            parser.error('location output must be a regular file, not a directory or symbolic link')
    return args


def main() -> int:
    args = parse_args()

    # Handle --list-types
    if args.list_types:
        print("Known frame types:")
        for ft in FrameType:
            if ft == FrameType.RAW:
                continue
            optional = " (optional, use --include)" if ft in OPTIONAL_PARSED_TYPES else ""
            print(f"  {ft.value:3d}: {ft.name}{optional}")
        return 0

    input_files = args.input
    exiftool = None
    if args.set_exif_location:
        if args.exiftool is not None:
            exiftool = shutil.which(args.exiftool)
            if exiftool is None:
                print(f'Error: ExifTool executable not found: {args.exiftool}', file=sys.stderr)
                return 1
        output_exists = bool(args.output and os.path.lexists(args.output))
        same_input = bool(args.output and (
            os.path.abspath(args.output) == os.path.abspath(input_files[0]) or
            (output_exists and os.path.exists(input_files[0]) and
             os.path.samefile(args.output, input_files[0]))))
        prompt = None
        if not args.output or same_input:
            prompt = (f'WARNING: This will modify {len(input_files)} input file(s). '
                      'Make sure you have a backup. '
                      + ('The Python writer may be incompatible with other INSV versions. '
                         if exiftool is None else '') + 'Press y to continue: ')
        elif output_exists:
            prompt = f'Output file {args.output} already exists. Overwrite? [y/n]: '
        if prompt and not args.yes:
            print(prompt, file=sys.stderr, end='', flush=True)
            if sys.stdin.readline().strip().lower() != 'y':
                print('Cancelled; no files were modified.', file=sys.stderr)
                return 1

    # Handle --scan (supports multiple files)
    if args.scan:
        errors = 0
        for input_file in input_files:
            try:
                with open(input_file, 'rb') as f:
                    metadata = InsvMetadata.read(f)
                if metadata is None:
                    print(f"{input_file}: No valid INSV metadata found", file=sys.stderr)
                    errors += 1
                else:
                    scan_frame_types(input_file, metadata)
            except Exception as e:
                print(f"{input_file}: Error - {e}", file=sys.stderr)
                errors += 1
        return 1 if errors else 0

    if args.location is not None:
        errors = 0
        geocoder = Geocoder()
        for input_file in input_files:
            entry = {'path': os.path.abspath(input_file)}
            try:
                with open(input_file, 'rb') as f:
                    metadata = InsvMetadata.read(f)
                if metadata is None:
                    raise ValueError('No valid INSV metadata found')
                location = find_location(metadata, args.location)
                if location is None:
                    raise ValueError('No valid active GPS location found within 60 seconds of requested time')
                entry.update(location)
                if args.set_exif_location:
                    if args.output:
                        set_location(input_file, location, exiftool, output=args.output,
                                     overwrite=output_exists)
                        entry['output'] = os.path.abspath(args.output)
                    else:
                        set_location(input_file, location, exiftool)
                    entry['modified'] = True
                    print(f'Location written to {args.output or input_file}', file=sys.stderr)
                try:
                    entry['locationName'] = geocoder.lookup(location['latitude'], location['longitude'])
                except Exception as e:
                    # A name lookup failure must not hide the GPS fix or prevent
                    # an otherwise valid metadata write.
                    entry['locationName'] = f'unavailable ({e})'
                    print(f'{input_file}: Place lookup failed - {e}', file=sys.stderr)
                    errors += 1
            except Exception as e:
                entry['error'] = str(e)
                print(f'{input_file}: Error - {e}', file=sys.stderr)
                errors += 1
            try:
                print(format_location(entry) + '\n', flush=True)
            except OSError as e:
                print(f'Error writing output: {e}', file=sys.stderr)
                return 1
        try:
            print(ATTRIBUTION, flush=True)
        except OSError as e:
            print(f'Error writing output: {e}', file=sys.stderr)
            return 1
        return 1 if errors else 0

    # Full metadata and single-frame dumps accept one input file.
    if len(input_files) > 1:
        print("Error: Multiple files only supported with --scan or --location", file=sys.stderr)
        return 1

    input_file = input_files[0]

    # Check input file exists
    if not os.path.isfile(input_file):
        print(f"Error: File not found: {input_file}", file=sys.stderr)
        return 1

    # Parse include types
    include_types = parse_include_types(args.include)

    # Read metadata
    try:
        with open(input_file, 'rb') as f:
            metadata = InsvMetadata.read(f)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        return 1

    if metadata is None:
        print(f"Error: No valid INSV metadata found in {input_file}", file=sys.stderr)
        return 1

    # Parse metadata
    try:
        metadata.parse(include_types if include_types else None)
    except Exception as e:
        print(f"Error parsing metadata: {e}", file=sys.stderr)
        return 1

    # Determine what to dump
    if args.frame_type is not None:
        frame = metadata.find_frame_by_code(args.frame_type)
        if frame is None:
            print(f"Error: Frame type {args.frame_type} not found", file=sys.stderr)
            return 1
        output_json = dump_frame(frame)
        default_suffix = f".frame{args.frame_type}.meta.json"
    else:
        output_json = dump_metadata(metadata)
        default_suffix = ".meta.json"

    output_file = args.output or (os.path.basename(input_file) + default_suffix)
    return write_output(output_json, output_file)


def write_output(output_json: str, output_file: str) -> int:
    """Write JSON, keeping diagnostics on stderr."""
    if output_file == '-':
        try:
            sys.stdout.write(output_json + '\n')
        except OSError as e:
            print(f'Error writing output: {e}', file=sys.stderr)
            return 1
        return 0

    # Check if output file exists
    if os.path.exists(output_file):
        print(f"Error: File {output_file} already exists", file=sys.stderr)
        return 1

    # Write output
    try:
        with open(output_file, 'w') as f:
            f.write(output_json)
            f.write('\n')
        print(f"Metadata dumped to {output_file}", file=sys.stderr)
    except Exception as e:
        print(f"Error writing output: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
