"""Cached, serialized place-name Nominatim lookups for occasional CLI use."""

import json
import os
from pathlib import Path
import sqlite3
import ssl
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_ENDPOINT = 'https://nominatim.openstreetmap.org/reverse'
LOOKUP_ZOOM = 17  # Street-level ceiling: do not request buildings/house addresses.
LOOKUP_LAYERS = 'address,poi,natural'
NAME_VERSION = 2
USER_AGENT = 'insvtool/0.1 (+https://github.com/ke4ukz/insvtool)'
ATTRIBUTION = ('Location names and maps: © OpenStreetMap contributors (ODbL), '
               'https://www.openstreetmap.org/copyright')


def place_name(data):
    """Pick a named feature or settlement, excluding street/house addresses."""
    address = data.get('address', {})
    feature = next((address[key] for key in (
        'national_park', 'protected_area', 'nature_reserve', 'park', 'island', 'islet', 'archipelago'
    ) if address.get(key)), None)
    named_feature = (data.get('category') in (
        'natural', 'leisure', 'tourism', 'historic', 'amenity', 'place') or
        (data.get('category') == 'boundary' and data.get('type') in (
            'protected_area', 'national_park', 'nature_reserve')))
    if feature is None and named_feature:
        if data.get('addresstype') not in ('house', 'house_number', 'building', 'road', 'street', 'postcode'):
            feature = data.get('name')
    locality = next((address[key] for key in (
        'hamlet', 'neighbourhood', 'quarter', 'suburb', 'village', 'town',
        'city_district', 'city', 'municipality', 'county'
    ) if address.get(key)), None)
    # A county adds little when there is already a specific landmark name.
    if feature and locality == address.get('county'):
        locality = None
    parts = [feature, locality, address.get('state'), address.get('country')]
    name = ', '.join(dict.fromkeys(part for part in parts if part))
    if not name:
        raise ValueError('No place name returned')
    return name


class Geocoder:
    def __init__(self, cache_path=None, endpoint=None):
        self.cache_path = Path(cache_path or os.environ.get(
            'INSVTOOL_LOCATION_CACHE', str(Path.home() / '.insvtool_location_cache.db')))
        self.endpoint = endpoint or os.environ.get('INSVTOOL_NOMINATIM_URL', DEFAULT_ENDPOINT)

    def lookup(self, latitude, longitude):
        # Query the cell's rounded coordinates too, so a cache result is exactly
        # the response for its key, not an arbitrary point within that cell.
        lat = f'{round(latitude, 3) + 0.0:.3f}'
        lon = f'{round(longitude, 3) + 0.0:.3f}'
        key = json.dumps([self.endpoint, lat, lon, 'en', LOOKUP_ZOOM, LOOKUP_LAYERS, NAME_VERSION])
        with sqlite3.connect(self.cache_path, timeout=30) as db:
            db.execute('CREATE TABLE IF NOT EXISTS locations (key TEXT PRIMARY KEY, name TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY, started REAL NOT NULL)')
            # The lock serializes requests even across simultaneous local runs.
            db.execute('BEGIN IMMEDIATE')
            cached = db.execute('SELECT name FROM locations WHERE key=?', (key,)).fetchone()
            if cached:
                return cached[0]
            last = db.execute('SELECT started FROM requests WHERE id=1').fetchone()
            if last:
                delay = 1.05 - (time.time() - last[0])
                if delay > 0:
                    time.sleep(delay)
            started = time.time()
            db.execute('INSERT OR REPLACE INTO requests VALUES (1, ?)', (started,))
            try:
                url = self.endpoint + '?' + urlencode({
                    'lat': lat, 'lon': lon, 'format': 'jsonv2', 'zoom': LOOKUP_ZOOM,
                    'addressdetails': 1, 'accept-language': 'en', 'layer': LOOKUP_LAYERS})
                request = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
                context = ssl.create_default_context()
                if (sys.platform == 'darwin' and ssl.get_default_verify_paths().cafile is None
                        and not os.environ.get('SSL_CERT_FILE') and Path('/etc/ssl/cert.pem').is_file()):
                    # Some python.org installations lack their own CA bundle.
                    # Use the OS bundle, never an unverified SSL context.
                    context.load_verify_locations('/etc/ssl/cert.pem')
                with urlopen(request, timeout=10, context=context) as response:
                    data = json.load(response)
                if 'error' in data:
                    raise ValueError(data['error'])
                name = place_name(data)
                db.execute('INSERT OR REPLACE INTO locations VALUES (?, ?)', (key, name))
                return name
            finally:
                # Failed requests are rate-limited too; only successful results
                # are cached. Commit while still holding the request lock.
                db.commit()
