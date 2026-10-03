"""Nominatim requests, caching, and timing without external network access."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from insvtool.geocode import Geocoder, USER_AGENT, place_name


class GeocoderTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache = Path(directory.name) / 'cache.db'
        self.clock = [100.0]
        self.requests = []
        self.sleeps = []

    def respond(self, request, timeout, context):
        self.requests.append(request)
        self.assertEqual(timeout, 10)
        return io.BytesIO(json.dumps({'address': {
            'town': 'Eastpoint', 'state': 'Florida', 'country': 'United States'
        }}).encode())

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.clock[0] += duration

    def test_rounding_and_persistent_cache(self):
        with patch('insvtool.geocode.urlopen', side_effect=self.respond):
            first = Geocoder(self.cache).lookup(29.6782976, -84.8725769)
            second = Geocoder(self.cache).lookup(29.67831, -84.87259)
        self.assertEqual(first, 'Eastpoint, Florida, United States')
        self.assertEqual(second, first)
        self.assertEqual(len(self.requests), 1)
        parameters = parse_qs(urlparse(self.requests[0].full_url).query)
        self.assertEqual(parameters['lat'], ['29.678'])
        self.assertEqual(parameters['lon'], ['-84.873'])
        self.assertEqual(parameters['zoom'], ['17'])
        self.assertEqual(parameters['layer'], ['address,poi,natural'])
        self.assertEqual(self.requests[0].get_header('User-agent'), USER_AGENT)

    def test_elapsed_extraction_time_counts_toward_limit(self):
        with patch('insvtool.geocode.urlopen', side_effect=self.respond), \
                patch('insvtool.geocode.time.time', side_effect=lambda: self.clock[0]), \
                patch('insvtool.geocode.time.sleep', side_effect=self.sleep):
            Geocoder(self.cache).lookup(1, 2)
            self.clock[0] += 0.4  # Time spent finding coordinates in the next video.
            Geocoder(self.cache).lookup(3, 4)
            self.assertAlmostEqual(self.sleeps[0], 0.65)
            self.clock[0] += 2  # Slow extraction needs no additional wait.
            Geocoder(self.cache).lookup(5, 6)
            self.assertEqual(len(self.sleeps), 1)

    def test_failed_requests_are_not_cached_but_are_rate_limited(self):
        with patch('insvtool.geocode.time.time', side_effect=lambda: self.clock[0]), \
                patch('insvtool.geocode.time.sleep', side_effect=self.sleep):
            with patch('insvtool.geocode.urlopen', side_effect=OSError('offline')):
                with self.assertRaises(OSError):
                    Geocoder(self.cache).lookup(1, 2)
            with patch('insvtool.geocode.urlopen', side_effect=self.respond):
                Geocoder(self.cache).lookup(1, 2)
            self.assertAlmostEqual(self.sleeps[0], 1.05)

    def test_named_features_and_locality_fallbacks(self):
        examples = [
            ({'category': 'boundary', 'type': 'protected_area', 'name': 'Example State Park',
              'address': {'county': 'County', 'state': 'Florida'}}, 'Example State Park, Florida'),
            ({'category': 'leisure', 'name': 'Example State Park',
              'address': {'village': 'Nearby Village', 'county': 'County', 'state': 'Florida'}},
             'Example State Park, Nearby Village, Florida'),
            ({'category': 'highway', 'name': 'Wrong Road', 'address': {
                'house_number': '123', 'road': 'Wrong Road', 'island': 'Saint George Island',
                'county': 'Franklin County', 'state': 'Florida'}}, 'Saint George Island, Florida'),
            ({'address': {'neighbourhood': 'Small Neighbourhood', 'town': 'Larger Town',
                          'state': 'Florida'}}, 'Small Neighbourhood, Florida'),
            ({'category': 'building', 'name': '123 Main Street', 'display_name': '123 Main Street',
              'address': {'house_number': '123', 'road': 'Main Street', 'town': 'Eastpoint'}}, 'Eastpoint'),
            ({'address': {'county': 'Franklin County', 'state': 'Florida'}}, 'Franklin County, Florida'),
        ]
        for data, expected in examples:
            with self.subTest(data=data):
                self.assertEqual(place_name(data), expected)
        with self.assertRaises(ValueError):
            place_name({'display_name': '123 Main Street', 'address': {'house_number': '123', 'road': 'Main Street'}})

    def test_old_city_cache_does_not_mask_detailed_lookup(self):
        import sqlite3
        with sqlite3.connect(self.cache) as db:
            db.execute('CREATE TABLE locations (key TEXT PRIMARY KEY, name TEXT NOT NULL)')
            old_key = json.dumps(['https://nominatim.openstreetmap.org/reverse', '1.000', '2.000', 'en', 10])
            db.execute('INSERT INTO locations VALUES (?, ?)', (old_key, 'Old County'))
        with patch('insvtool.geocode.urlopen', side_effect=self.respond):
            self.assertEqual(Geocoder(self.cache).lookup(1, 2), 'Eastpoint, Florida, United States')
        self.assertEqual(len(self.requests), 1)

    def test_alternative_endpoint_has_separate_cache(self):
        with patch('insvtool.geocode.urlopen', side_effect=self.respond):
            Geocoder(self.cache).lookup(1, 2)
            Geocoder(self.cache, 'https://example.org/reverse').lookup(1, 2)
        self.assertEqual(len(self.requests), 2)


if __name__ == '__main__':
    unittest.main()
