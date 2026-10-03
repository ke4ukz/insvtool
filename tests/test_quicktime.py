"""Verify direct writes preserve media offsets, unknown metadata, and trailers."""

from pathlib import Path
import struct
import os
import time
import tempfile
import unittest

from insvtool.header import HEADER_SIZE, SIGNATURE
from insvtool.quicktime import atom, boxes, read_location, write_location, LOCATION_KEY
from insvtool.set_location import set_location, trailer_digest


def trailer():
    return bytes(32) + struct.pack('<II', HEADER_SIZE, 3) + SIGNATURE


def movie(offset, metadata=b''):
    stco = atom(b'stco', bytes(4) + struct.pack('>II', 1, offset))
    return atom(b'moov', atom(b'trak', atom(b'mdia', atom(b'minf', atom(b'stbl', stco)))) + metadata)


class QuickTimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'video.insv'
        self.output = Path(self.directory.name) / 'edited.insv'

    def test_movie_before_and_after_media_and_repeated_writes(self):
        for before in (False, True):
            with self.subTest(before=before):
                ftyp = atom(b'ftyp', b'isom' + bytes(4))
                media = atom(b'mdat', b'encoded media bytes')
                moov = movie(0, atom(b'udta', atom(b'zzzz', b'keep me')))
                offset = len(ftyp) + (len(moov) if before else 0) + 8
                moov = movie(offset, atom(b'udta', atom(b'zzzz', b'keep me')))
                original = ftyp + (moov + media if before else media + moov) + trailer()
                self.path.write_bytes(original)
                for latitude in (40.5, -12.25):
                    set_location(self.path, {'latitude': latitude, 'longitude': -73.25})
                    result = self.path.read_bytes()
                    self.assertEqual(result[offset:offset + len(b'encoded media bytes')], b'encoded media bytes')
                    self.assertIn(atom(b'stco', bytes(4) + struct.pack('>II', 1, offset)), result)
                    self.assertIn(atom(b'zzzz', b'keep me'), result)
                    self.assertTrue(result.endswith(trailer()))
                    self.assertEqual(read_location(self.path), f'{latitude:+012.8f}-073.25000000/')
                    self.assertEqual(result.count(LOCATION_KEY), 1)

    def test_existing_keys_and_other_items_preserved(self, fullbox=True):
        handler = atom(b'hdlr', bytes(8) + b'mdta' + bytes(13))
        keys = atom(b'keys', bytes(4) + struct.pack('>I', 2) +
                    atom(b'mdta', b'com.apple.quicktime.title') + atom(b'mdta', LOCATION_KEY))
        title = atom(struct.pack('>I', 1), atom(b'data', struct.pack('>II', 1, 0) + b'Test title'))
        old_location = atom(struct.pack('>I', 2), atom(b'data', struct.pack('>II', 1, 0) + b'+01+002/'))
        meta = atom(b'meta', (bytes(4) if fullbox else b'') + handler + keys + atom(b'ilst', title + old_location))
        self.path.write_bytes(atom(b'ftyp', b'isom' + bytes(4)) + atom(b'mdat', b'media') +
                              movie(24, atom(b'udta', meta)) + trailer())
        set_location(self.path, {'latitude': 1.25, 'longitude': 2.5})
        result = self.path.read_bytes()
        self.assertIn(title, result)
        self.assertEqual(result.count(LOCATION_KEY), 1)
        # Existing ISO-style metadata is converted to Apple's QuickTime layout.
        self.assertIn(atom(b'meta', handler + keys + atom(b'ilst', title +
            atom(struct.pack('>I', 2), atom(b'data', struct.pack('>II', 1, 0) +
                 b'+01.25000000+002.50000000/')))), result)
        self.assertEqual(read_location(self.path), '+01.25000000+002.50000000/')

    def test_new_metadata_uses_quicktime_layout_for_apple_readers(self):
        self.path.write_bytes(atom(b'ftyp', b'isom' + bytes(4)) +
                              atom(b'mdat', b'media') + movie(24) + trailer())
        set_location(self.path, {'latitude': 1, 'longitude': 2})
        data = self.path.read_bytes()[:-len(trailer())]
        moov = next(p for k, p, raw in boxes(data) if k == b'moov')
        meta = next(p for k, p, raw in boxes(moov) if k == b'meta')
        self.assertEqual(meta[4:8], b'hdlr')
        handler = next(p for k, p, raw in boxes(meta) if k == b'hdlr')
        self.assertEqual(len(handler), 24)
        self.assertEqual(handler[8:12], b'mdta')

    def test_quicktime_metadata_without_fullbox_version(self):
        self.test_existing_keys_and_other_items_preserved(fullbox=False)

    def test_modification_time_updates_for_copy_and_in_place(self):
        original = atom(b'ftyp', b'isom' + bytes(4)) + atom(b'mdat', b'media') + movie(24) + trailer()
        self.path.write_bytes(original)
        old_time = 1700000000
        os.utime(self.path, (old_time, old_time))
        before = time.time_ns()
        set_location(self.path, {'latitude': 1, 'longitude': 2}, output=self.output)
        self.assertEqual(self.path.stat().st_mtime, old_time)
        self.assertGreaterEqual(self.output.stat().st_mtime_ns, before)
        self.assertEqual(self.path.read_bytes(), original)
        set_location(self.path, {'latitude': 1, 'longitude': 2})
        self.assertGreaterEqual(self.path.stat().st_mtime_ns, before)

    def test_failed_write_preserves_existing_destination(self):
        original = atom(b'moov', atom(b'mvex', b'')) + trailer()
        self.path.write_bytes(original)
        self.output.write_bytes(b'keep destination')
        with self.assertRaises(ValueError):
            set_location(self.path, {'latitude': 1, 'longitude': 2},
                         output=self.output, overwrite=True)
        self.assertEqual(self.output.read_bytes(), b'keep destination')
        self.assertEqual(self.path.read_bytes(), original)

    def test_unsupported_layout_leaves_original_unchanged(self):
        for container in (atom(b'moov', atom(b'mvex', b'')), atom(b'moof', b''),
                          movie(0) + movie(0), struct.pack('>I4s', 0, b'mdat')):
            original = atom(b'ftyp', b'isom' + bytes(4)) + container + trailer()
            self.path.write_bytes(original)
            with self.assertRaises(ValueError):
                set_location(self.path, {'latitude': 1, 'longitude': 2})
            self.assertEqual(self.path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
