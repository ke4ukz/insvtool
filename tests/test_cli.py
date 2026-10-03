"""CLI integration checks using synthetic INSV metadata trailers."""

import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from insvtool.header import HEADER_SIZE, SIGNATURE


SCRIPT = Path(__file__).resolve().parents[1] / 'insvtool.py'


def gps_record(latitude=40.5, longitude=73.25, ns=b'N', ew=b'W', status=b'A'):
    return struct.pack('<qHc d c d c 3d', 1700000000, 0, status,
                       latitude, ns, longitude, ew, 0, 0, 0)


def insv_file(payloads):
    frames = b''.join(payload + struct.pack('<BBI', 1, 7, len(payload))
                      for payload in payloads)
    return frames + bytes(32) + struct.pack('<II', len(frames) + HEADER_SIZE, 3) + SIGNATURE


class CliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'video.insv'

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), str(self.path), *args],
                              cwd=self.directory.name, capture_output=True, text=True)

    def test_location_skips_void_and_invalid_fixes_across_frames(self):
        self.path.write_bytes(insv_file([
            gps_record(status=b'V') + gps_record(latitude=float('nan')),
            gps_record(latitude=91) + gps_record(ns=b'?', ew=b'?') +
            gps_record(latitude=-40.5, ns=b'S', ew=b'O') + gps_record(latitude=1),
        ]))
        result = self.run_cli('-l')
        self.assertEqual(result.returncode, 0, result.stderr)
        location = json.loads(result.stdout)[0]
        self.assertEqual(location['latitude'], -40.5)
        self.assertEqual(location['longitude'], -73.25)
        self.assertEqual(location['mapUrl'],
                         'https://www.openstreetmap.org/?mlat=-40.5&mlon=-73.25#map=16/-40.5/-73.25')
        self.assertEqual(result.stderr, '')

    def test_location_without_fix(self):
        self.path.write_bytes(insv_file([gps_record(status=b'V')]))
        result = self.run_cli('--location', '-o', '-')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)[0]['filename'], 'video.insv')
        self.assertIn('error', json.loads(result.stdout)[0])
        self.assertIn('No valid active GPS location', result.stderr)

    def test_location_file_and_overwrite_protection(self):
        self.path.write_bytes(insv_file([gps_record()]))
        result = self.run_cli('-l', '-o', 'location.json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        output = Path(self.directory.name) / 'location.json'
        self.assertEqual(json.loads(output.read_text())[0]['latitude'], 40.5)
        self.assertEqual(self.run_cli('-l', '-o', 'location.json').returncode, 1)

    def test_metadata_and_single_frame_stdout_with_warning(self):
        self.path.write_bytes(insv_file([gps_record()]))
        for options in ([], ['--frame-type', '7']):
            with self.subTest(options=options):
                result = self.run_cli(*options, '--include', 'NOT_A_TYPE', '-o', '-')
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(result.stdout)
                frame = data['frames'][0] if not options else data
                self.assertEqual(frame['records'][0]['latitude'], 40.5)
                self.assertIn('Warning:', result.stderr)
        self.assertFalse((Path(self.directory.name) / '-').exists())

    def test_multiple_locations_preserve_order_and_report_failures(self):
        self.path.write_bytes(insv_file([gps_record()]))
        second = Path(self.directory.name) / 'second.insv'
        second.write_bytes(insv_file([gps_record(latitude=12, ew=b'E')]))
        void = Path(self.directory.name) / 'void.insv'
        void.write_bytes(insv_file([gps_record(status=b'V')]))
        missing = Path(self.directory.name) / 'missing.insv'
        result = self.run_cli(str(second), str(void), str(missing), '-l')
        self.assertEqual(result.returncode, 1)
        entries = json.loads(result.stdout)
        self.assertEqual([entry['filename'] for entry in entries],
                         ['video.insv', 'second.insv', 'void.insv', 'missing.insv'])
        self.assertEqual(entries[1]['latitude'], 12)
        self.assertEqual(entries[1]['longitude'], 73.25)
        self.assertIn('error', entries[2])
        self.assertIn('error', entries[3])
        result = self.run_cli(str(second), '-l', '-o', 'locations.json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        entries = json.loads((Path(self.directory.name) / 'locations.json').read_text())
        self.assertEqual(len(entries), 2)

    def test_location_mode_conflicts(self):
        self.path.write_bytes(insv_file([gps_record()]))
        for options in (['--scan'], ['--list-types'], ['--frame-type', '7']):
            result = self.run_cli('-l', *options)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
