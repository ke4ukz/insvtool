"""CLI integration checks using synthetic INSV metadata trailers."""

import json
import contextlib
import importlib.util
import io
import os
import sqlite3
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from insvtool.header import HEADER_SIZE, SIGNATURE
from insvtool.proto.extra_metadata_pb2 import ExtraMetadata
from insvtool.geocode import DEFAULT_ENDPOINT, ATTRIBUTION, LOOKUP_ZOOM, LOOKUP_LAYERS, NAME_VERSION


SCRIPT = Path(__file__).resolve().parents[1] / 'insvtool.py'


def report_entries(text):
    entries = []
    for block in text.strip().split('\n\n'):
        if block.startswith('Location names and maps:'):
            continue
        lines = block.splitlines()
        entry = {'path': lines[0], 'filename': Path(lines[0]).name}
        for line in lines[1:]:
            key, value = line.strip().split(': ', 1)
            if key == 'Coordinates':
                entry['latitude'], entry['longitude'] = map(float, value.split(', '))
            elif key == 'Map':
                entry['mapUrl'] = value
            elif key == 'Error':
                entry['error'] = value
            elif key == 'Written':
                entry['modified'] = True
                entry['output'] = Path(value).name
        entries.append(entry)
    return entries


def gps_record(latitude=40.5, longitude=73.25, ns=b'N', ew=b'W', status=b'A', time=1700000000):
    return struct.pack('<IIHc d c d c 3d', int(time), 0, round((time % 1) * 1000), status,
                       latitude, ns, longitude, ew, 0, 0, 0)


def insv_file(payloads, start=None, duration=None):
    frames = b''.join(payload + struct.pack('<BBI', 1, 7, len(payload))
                      for payload in payloads)
    if start is not None:
        info = ExtraMetadata(FirstGpsTimestamp=round(start * 1000), TotalTime=duration)
        payload = info.SerializeToString()
        frames += payload + struct.pack('<BBI', 1, 1, len(payload))
    return frames + bytes(32) + struct.pack('<II', len(frames) + HEADER_SIZE, 3) + SIGNATURE


class CliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'video.insv'
        cache = Path(self.directory.name) / 'cache.db'
        with sqlite3.connect(cache) as db:
            db.execute('CREATE TABLE locations (key TEXT PRIMARY KEY, name TEXT NOT NULL)')
            for lat in (-40.5, 40.5, 12, 1, 2, 3, 4):
                for lon in (-73.25, 73.25):
                    key = json.dumps([DEFAULT_ENDPOINT, f'{lat:.3f}', f'{lon:.3f}', 'en', LOOKUP_ZOOM, LOOKUP_LAYERS, NAME_VERSION])
                    db.execute('INSERT INTO locations VALUES (?, ?)', (key, 'Test City, Test State, Test Country'))
        environment = patch.dict(os.environ, {'INSVTOOL_LOCATION_CACHE': str(cache)})
        environment.start()
        self.addCleanup(environment.stop)

    def run_cli(self, *args, input=None):
        return subprocess.run([sys.executable, str(SCRIPT), str(self.path), *args],
                              cwd=self.directory.name, capture_output=True, text=True, input=input)

    def test_location_skips_void_and_invalid_fixes_across_frames(self):
        self.path.write_bytes(insv_file([
            gps_record(status=b'V') + gps_record(latitude=float('nan')),
            gps_record(latitude=91) + gps_record(ns=b'?', ew=b'?') +
            gps_record(latitude=-40.5, ns=b'S', ew=b'O') + gps_record(latitude=1),
        ]))
        result = self.run_cli('-l')
        self.assertEqual(result.returncode, 0, result.stderr)
        location = report_entries(result.stdout)[0]
        self.assertEqual(location['latitude'], -40.5)
        self.assertEqual(location['longitude'], -73.25)
        self.assertEqual(location['mapUrl'],
                         'https://www.openstreetmap.org/?mlat=-40.5&mlon=-73.25#map=16/-40.5/-73.25')
        self.assertEqual(result.stderr, '')

    def test_location_without_fix(self):
        self.path.write_bytes(insv_file([gps_record(status=b'V')]))
        result = self.run_cli('--location', '-o', '-')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report_entries(result.stdout)[0]['filename'], 'video.insv')
        self.assertIn('error', report_entries(result.stdout)[0])
        self.assertIn('No valid active GPS location', result.stderr)

    def test_location_ignores_output_option(self):
        self.path.write_bytes(insv_file([gps_record()]))
        output = Path(self.directory.name) / 'location.json'
        output.write_text('leave this file alone')
        result = self.run_cli('-l', '-o', str(output))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report_entries(result.stdout)[0]['latitude'], 40.5)
        self.assertEqual(output.read_text(), 'leave this file alone')
        self.assertIn(str(self.path), result.stdout)
        self.assertIn('GPS date/time: 2023-11-14T22:13:20.000Z', result.stdout)
        self.assertIn('Location: Test City, Test State, Test Country', result.stdout)
        self.assertEqual(result.stdout.count(ATTRIBUTION), 1)

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
        entries = report_entries(result.stdout)
        self.assertEqual([entry['filename'] for entry in entries],
                         ['video.insv', 'second.insv', 'void.insv', 'missing.insv'])
        self.assertEqual(entries[1]['latitude'], 12)
        self.assertEqual(entries[1]['longitude'], 73.25)
        self.assertIn('error', entries[2])
        self.assertIn('error', entries[3])
        result = self.run_cli(str(second), '-l', '-o', 'locations.json')
        self.assertEqual(result.returncode, 0, result.stderr)
        entries = report_entries(result.stdout)
        self.assertEqual(len(entries), 2)
        self.assertFalse((Path(self.directory.name) / 'locations.json').exists())
        self.assertEqual(result.stdout.count(ATTRIBUTION), 1)

    def test_first_report_is_flushed_before_next_lookup(self):
        self.path.write_bytes(insv_file([gps_record()]))
        second = Path(self.directory.name) / 'second.insv'
        second.write_bytes(insv_file([gps_record(latitude=12)]))
        spec = importlib.util.spec_from_file_location('insvtool_cli', SCRIPT)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        class Output(io.StringIO):
            def __init__(self):
                super().__init__()
                self.flushes = 0
            def flush(self):
                self.flushes += 1
        stdout = Output()
        def lookup(latitude, longitude):
            if latitude == 12:
                self.assertIn(str(self.path), stdout.getvalue())
                self.assertIn('Location: First location', stdout.getvalue())
                self.assertGreater(stdout.flushes, 0)
                self.assertNotIn(ATTRIBUTION, stdout.getvalue())
            return 'First location' if latitude == 40.5 else 'Second location'
        with patch.object(sys, 'argv', [str(SCRIPT), str(self.path), str(second), '-l']), \
                patch.object(cli.Geocoder, 'lookup', side_effect=lookup), \
                contextlib.redirect_stdout(stdout):
            self.assertEqual(cli.main(), 0)
        self.assertEqual(stdout.getvalue().count(ATTRIBUTION), 1)
        self.assertTrue(stdout.getvalue().endswith(ATTRIBUTION + '\n'))

    def test_location_offsets_and_negative_zero(self):
        start = 1700000000
        self.path.write_bytes(insv_file([
            gps_record(latitude=1, time=start + 10),
            gps_record(latitude=2, time=start + 5400.125),
            gps_record(latitude=3, time=start + 7100),
            gps_record(latitude=4, time=start + 7199.5),
        ], start=start, duration=7200))
        for value, expected in [('0', 1), ('5400.125', 2), ('1:30:00.125', 2),
                                ('-100', 3), ('-0:01:40.000', 3), ('-0', 4)]:
            with self.subTest(value=value):
                result = self.run_cli('-l', value)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(report_entries(result.stdout)[0]['latitude'], expected)
                if value == '5400.125':
                    self.assertIn('Video time: 1:30:00.125', result.stdout)
                    self.assertIn('GPS date/time: 2023-11-14T23:43:20.125Z', result.stdout)
        result = self.run_cli('-l', '3600')
        self.assertEqual(result.returncode, 1)
        self.assertIn('within 60 seconds', result.stderr)
        for value in ('7201', '-7201'):
            result = self.run_cli('-l', value)
            self.assertEqual(result.returncode, 1)
            self.assertIn('outside the video duration', result.stderr)

    def test_location_window_boundary_and_delayed_fix(self):
        start = 1700000000
        for delta, expected in [(60, 0), (60.001, 1)]:
            self.path.write_bytes(insv_file([gps_record(time=start + delta)],
                                           start=start, duration=120))
            result = self.run_cli('-l')
            self.assertEqual(result.returncode, expected, result.stderr)
        self.path.write_bytes(insv_file([
            gps_record(latitude=1, time=start + 50),
            gps_record(latitude=2, time=start + 60.25),
        ], start=start, duration=120))
        result = self.run_cli('-l', '60')
        self.assertEqual(report_entries(result.stdout)[0]['latitude'], 2)

    def test_location_without_timing_metadata_and_bad_times(self):
        self.path.write_bytes(insv_file([gps_record()]))
        for value in ('10', '-0'):
            result = self.run_cli('-l', value)
            self.assertEqual(result.returncode, 1)
            self.assertIn('requires FirstGpsTimestamp', result.stderr)
        for value in ('nan', 'inf', '1:60:00', '1:00:60', 'hello'):
            result = self.run_cli('--location=' + value)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
        # Bare -l before filenames must retain both inputs.
        result = subprocess.run([sys.executable, str(SCRIPT), '-l', str(self.path),
                                 str(self.path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(report_entries(result.stdout)), 2)

    def test_set_location_confirmation_and_defaults(self):
        self.path.write_bytes(insv_file([gps_record()]))
        spec = importlib.util.spec_from_file_location('insvtool_cli', SCRIPT)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        for response, yes, expected_writes in [('n\n', False, 0), ('', False, 0),
                                              ('y\n', False, 1), ('', True, 1)]:
            with self.subTest(response=response, yes=yes):
                argv = [str(SCRIPT), str(self.path), '--set-exif-location']
                if yes:
                    argv.append('-y')
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(sys, 'argv', argv), patch.object(sys, 'stdin', io.StringIO(response)), \
                        patch.object(cli.shutil, 'which', return_value='/tool/exiftool'), \
                        patch.object(cli, 'set_location') as write, \
                        contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = cli.main()
                self.assertEqual(write.call_count, expected_writes)
                self.assertEqual(code, 0 if expected_writes else 1)
                if expected_writes:
                    self.assertTrue(report_entries(stdout.getvalue())[0]['modified'])
                    self.assertEqual(write.call_args.args[1]['latitude'], 40.5)
                else:
                    self.assertEqual(stdout.getvalue(), '')
                self.assertEqual('Make sure you have a backup' in stderr.getvalue(), not yes)

    def test_set_location_output_and_overwrite_prompts(self):
        from insvtool.quicktime import atom, read_location
        contents = (atom(b'ftyp', b'isom' + bytes(4)) + atom(b'mdat', b'media') +
                    atom(b'moov', b'') + insv_file([gps_record()]))
        self.path.write_bytes(contents)
        destination = Path(self.directory.name) / 'output.insv'
        result = self.run_cli('--set-exif-location', '-o', str(destination), input='')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Press y', result.stderr)
        self.assertNotIn('Overwrite?', result.stderr)
        self.assertEqual(self.path.read_bytes(), contents)
        self.assertEqual(read_location(destination), '+40.50000000-073.25000000/')
        self.assertEqual(report_entries(result.stdout)[0]['output'], 'output.insv')
        destination.write_bytes(b'existing output')
        for answer in ('n\n', ''):
            result = self.run_cli('--set-exif-location', '-o', str(destination), input=answer)
            self.assertEqual(result.returncode, 1)
            self.assertIn('Overwrite?', result.stderr)
            self.assertEqual(destination.read_bytes(), b'existing output')
            self.assertEqual(result.stdout, '')
        result = self.run_cli('--set-exif-location', '-o', str(destination), input='y\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(destination.read_bytes(), b'existing output')
        destination.write_bytes(b'existing output')
        result = self.run_cli('--set-exif-location', '-o', str(destination), '-y', input='')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Overwrite?', result.stderr)
        self.assertEqual(self.path.read_bytes(), contents)
        result = self.run_cli('--set-exif-location', '-o', str(self.path), input='n\n')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Make sure you have a backup', result.stderr)
        self.assertEqual(self.path.read_bytes(), contents)

    def test_set_location_output_invalid_and_failed_lookup(self):
        self.path.write_bytes(insv_file([gps_record(status=b'V')]))
        destination = Path(self.directory.name) / 'output.insv'
        destination.write_bytes(b'keep this output')
        result = self.run_cli('--set-exif-location', '-o', str(destination), '-y')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(destination.read_bytes(), b'keep this output')
        for options in (['-o', '-'], ['-o', self.directory.name],
                        [str(self.path), '-o', str(destination)]):
            result = self.run_cli('--set-exif-location', *options, '-y')
            self.assertEqual(result.returncode, 2, result.stderr)

    def test_exiftool_backend_selection(self):
        self.path.write_bytes(insv_file([gps_record()]))
        spec = importlib.util.spec_from_file_location('insvtool_cli', SCRIPT)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        for option in (['--exiftool'], ['--exiftool', '/custom/exiftool'],
                       ['--exiftool=/custom/exiftool']):
            argv = [str(SCRIPT), '--set-exif-location', '-y', *option, str(self.path)]
            with patch.object(sys, 'argv', argv), \
                    patch.object(cli.shutil, 'which', return_value='/resolved/exiftool') as lookup, \
                    patch.object(cli, 'set_location') as write, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(), 0)
                self.assertEqual(write.call_args.args[2], '/resolved/exiftool')
                lookup.assert_called_once_with('exiftool' if len(option) == 1 and '=' not in option[0]
                                               else '/custom/exiftool')
        argv = [str(SCRIPT), '--set-exif-location', '-y', '--exiftool', str(self.path)]
        with patch.object(sys, 'argv', argv), patch.object(cli.shutil, 'which', return_value=None), \
                patch.object(cli, 'set_location') as write, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(), 1)
            write.assert_not_called()

    def test_set_location_failure_keeps_original(self):
        from insvtool.set_location import set_location
        contents = insv_file([gps_record()])
        self.path.write_bytes(contents)
        with patch('insvtool.set_location.run_exiftool', side_effect=ValueError('write failed')):
            with self.assertRaisesRegex(ValueError, 'write failed'):
                set_location(self.path, {'latitude': 1, 'longitude': 2}, '/tool/exiftool')
        self.assertEqual(self.path.read_bytes(), contents)
        self.assertEqual(sorted(p.name for p in Path(self.directory.name).iterdir()), ['cache.db', 'video.insv'])

    def test_set_location_rejects_changed_trailer(self):
        from insvtool.set_location import set_location
        contents = insv_file([gps_record()])
        self.path.write_bytes(contents)
        def corrupt(executable, *args):
            edited = Path(args[-1])
            data = bytearray(edited.read_bytes())
            data[0] ^= 1
            edited.write_bytes(data)
            return ''
        with patch('insvtool.set_location.run_exiftool', side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, 'changed the Insta360 trailer'):
                set_location(self.path, {'latitude': 1, 'longitude': 2}, '/tool/exiftool')
        self.assertEqual(self.path.read_bytes(), contents)

    def test_place_lookup_failure_keeps_coordinates(self):
        self.path.write_bytes(insv_file([gps_record()]))
        spec = importlib.util.spec_from_file_location('insvtool_cli', SCRIPT)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, 'argv', [str(SCRIPT), str(self.path), '-l']), \
                patch.object(cli.Geocoder, 'lookup', side_effect=OSError('offline')), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(cli.main(), 1)
        self.assertIn('Coordinates: 40.50000000, -73.25000000', stdout.getvalue())
        self.assertIn('Location: unavailable (offline)', stdout.getvalue())
        self.assertEqual(stdout.getvalue().count(ATTRIBUTION), 1)

    def test_location_mode_conflicts(self):
        self.path.write_bytes(insv_file([gps_record()]))
        for options in (['--scan'], ['--list-types'], ['--frame-type', '7']):
            result = self.run_cli('-l', *options)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
