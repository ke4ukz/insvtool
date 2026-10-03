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
import json
import os
import sys
from typing import List, Optional, Set

# Add the package directory to the path for standalone execution
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from insvtool.metadata import InsvMetadata
from insvtool.dump import dump_metadata, dump_frame
from insvtool.frames.frame_types import FrameType, OPTIONAL_PARSED_TYPES
from insvtool.location import find_location


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


def main() -> int:
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
  %(prog)s -l *.insv                       Print locations for multiple files

Available frame types for --include:
  MAGNETIC, EULER, GYRO_SECONDARY, SPEED, HEARTRATE, EXPOSURE_SECONDARY, POS
"""
    )
    parser.add_argument('input', nargs='*', help='Input INSV file(s)')
    parser.add_argument('-o', '--output',
                        help='Output JSON file, or - for stdout (location defaults to stdout)')
    parser.add_argument('-l', '--location', action='store_true',
                        help='Output a JSON array of filenames, first active GPS fixes, and map links')
    parser.add_argument('--frame-type', type=int, metavar='CODE',
                        help='Dump only the specified frame type (by numeric code)')
    parser.add_argument('--include', action='append', default=[], metavar='TYPES',
                        help='Include additional frame types for parsing (comma-separated)')
    parser.add_argument('--list-types', action='store_true',
                        help='List all known frame types and exit')
    parser.add_argument('--scan', action='store_true',
                        help='Scan file and show frame types present (no dump)')

    args = parser.parse_args()

    if args.location and (args.scan or args.list_types or args.frame_type is not None):
        parser.error('--location cannot be combined with --scan, --list-types, or --frame-type')

    # Handle --list-types
    if args.list_types:
        print("Known frame types:")
        for ft in FrameType:
            if ft == FrameType.RAW:
                continue
            optional = " (optional, use --include)" if ft in OPTIONAL_PARSED_TYPES else ""
            print(f"  {ft.value:3d}: {ft.name}{optional}")
        return 0

    # Check input file is provided
    if not args.input:
        parser.error("the following arguments are required: input")

    input_files = args.input

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

    if args.location:
        results = []
        errors = 0
        for input_file in input_files:
            entry = {'filename': os.path.basename(input_file)}
            try:
                with open(input_file, 'rb') as f:
                    metadata = InsvMetadata.read(f)
                if metadata is None:
                    raise ValueError('No valid INSV metadata found')
                location = find_location(metadata)
                if location is None:
                    raise ValueError('No valid active GPS location found')
                entry.update(location)
            except Exception as e:
                entry['error'] = str(e)
                print(f'{input_file}: Error - {e}', file=sys.stderr)
                errors += 1
            results.append(entry)
        status = write_output(json.dumps(results, indent=2), args.output or '-')
        return 1 if errors else status

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
