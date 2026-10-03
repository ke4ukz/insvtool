"""Focused QuickTime location writer for non-fragmented INSV containers."""

import os
import shutil
import struct

from .header import InsvHeader

LOCATION_KEY = b'com.apple.quicktime.location.ISO6709'


def atom(kind, payload):
    size = len(payload) + 8
    if size > 0xffffffff:
        return struct.pack('>I4sQ', 1, kind, len(payload) + 16) + payload
    return struct.pack('>I4s', size, kind) + payload


def boxes(data):
    """Yield validated box type, payload, and original bytes."""
    position = 0
    while position < len(data):
        if len(data) - position < 8:
            raise ValueError('Truncated QuickTime box')
        size, kind = struct.unpack_from('>I4s', data, position)
        header = 8
        if size == 1:
            if len(data) - position < 16:
                raise ValueError('Truncated extended QuickTime box')
            size = struct.unpack_from('>Q', data, position + 8)[0]
            header = 16
        if size < header or position + size > len(data):
            raise ValueError('Unsupported or invalid QuickTime box size')
        yield kind, data[position + header:position + size], data[position:position + size]
        position += size


def meta_parts(payload):
    # ISO meta is a FullBox; the older QuickTime variant has no version word.
    prefix = bytes(4) if payload[:4] == bytes(4) else b''
    return prefix, list(boxes(payload[len(prefix):]))


def edit_meta(payload, value):
    prefix, children = meta_parts(payload)
    keys = [p for k, p, raw in children if k == b'keys']
    lists = [p for k, p, raw in children if k == b'ilst']
    if len(keys) != 1 or len(lists) > 1:
        raise ValueError('Unsupported QuickTime metadata layout')
    key_data = keys[0]
    if len(key_data) < 8 or key_data[:4] != bytes(4):
        raise ValueError('Unsupported QuickTime key table')
    count = struct.unpack_from('>I', key_data, 4)[0]
    entries = list(boxes(key_data[8:]))
    if count != len(entries):
        raise ValueError('Invalid QuickTime key count')
    matches = [i + 1 for i, (k, p, raw) in enumerate(entries)
               if k == b'mdta' and p == LOCATION_KEY]
    if len(matches) > 1:
        raise ValueError('Duplicate QuickTime location keys')
    if matches:
        index = matches[0]
    else:
        entries.append((b'mdta', LOCATION_KEY, atom(b'mdta', LOCATION_KEY)))
        index = len(entries)
    key_box = atom(b'keys', bytes(4) + struct.pack('>I', len(entries)) +
                   b''.join(raw for k, p, raw in entries))
    item_type = struct.pack('>I', index)
    items = list(boxes(lists[0])) if lists else []
    item = atom(item_type, atom(b'data', struct.pack('>II', 1, 0) + value))
    list_box = atom(b'ilst', b''.join(raw for k, p, raw in items if k != item_type) + item)
    # Apple AVFoundation ignores ISO FullBox-style mdta in these videos.
    # Write the QuickTime variant, normalizing older output on updates.
    return atom(b'meta', b''.join(
        key_box if k == b'keys' else list_box if k == b'ilst' else raw
        for k, p, raw in children) + (list_box if not lists else b''))


def is_mdta(payload):
    prefix, children = meta_parts(payload)
    handlers = [p for k, p, raw in children if k == b'hdlr']
    return any(len(p) >= 12 and p[8:12] == b'mdta' for p in handlers)


def edit_moov(payload, value):
    found = 0
    def edit_children(data, nested=False):
        nonlocal found
        result = []
        for kind, child, raw in boxes(data):
            if kind == b'mvex':
                raise ValueError('Fragmented QuickTime containers are not supported')
            if kind == b'meta' and is_mdta(child):
                found += 1
                result.append(edit_meta(child, value))
            elif kind == b'udta' and not nested:
                result.append(atom(kind, edit_children(child, True)))
            else:
                result.append(raw)
        return b''.join(result)
    updated = edit_children(payload)
    if found > 1:
        raise ValueError('Multiple QuickTime mdta containers are not supported')
    if not found:
        handler = atom(b'hdlr', bytes(8) + b'mdta' + bytes(12))
        keys = atom(b'keys', bytes(4) + struct.pack('>I', 0))
        updated += edit_meta(handler + keys, value)
    return atom(b'moov', updated)


def copy_bytes(source, destination, size):
    while size:
        chunk = source.read(min(size, 1024 * 1024))
        if not chunk:
            raise ValueError('Unexpected end of video file')
        destination.write(chunk)
        size -= len(chunk)


def write_location(source_path, destination_path, location):
    """Relocate moov if needed, keeping media offsets and trailer bytes intact."""
    value = (f"{location['latitude']:+012.8f}{location['longitude']:+013.8f}/").encode('ascii')
    with open(source_path, 'rb') as source:
        source.seek(0, os.SEEK_END)
        header = InsvHeader.read(source, source.tell())
        if header is None:
            raise ValueError('No INSV trailer found')
        end = header.metadata_pos
        position = 0
        moov = None
        while position < end:
            source.seek(position)
            raw = source.read(8)
            if len(raw) != 8:
                raise ValueError('Truncated QuickTime container')
            size, kind = struct.unpack('>I4s', raw)
            box_header = 8
            if size == 1:
                extended = source.read(8)
                if len(extended) != 8:
                    raise ValueError('Truncated extended box')
                size = struct.unpack('>Q', extended)[0]
                box_header = 16
            if size < box_header or position + size > end:
                raise ValueError('Unsupported QuickTime container layout')
            if kind in (b'moof', b'mfra'):
                raise ValueError('Fragmented QuickTime containers are not supported')
            if kind == b'moov':
                if moov is not None or size > 64 * 1024 * 1024:
                    raise ValueError('Unsupported movie metadata layout')
                moov = (position, size, edit_moov(source.read(size - box_header), value))
            position += size
        if moov is None:
            raise ValueError('No QuickTime movie metadata found')
        position, size, replacement = moov
        with open(destination_path, 'wb') as destination:
            source.seek(0)
            copy_bytes(source, destination, position)
            if position + size == end:
                destination.write(replacement)
                source.seek(end)
            else:
                # Leave the old box in place as free space. Absolute media
                # offsets still point to exactly the same bytes.
                destination.write(struct.pack('>I4sQ', 1, b'free', size) if size > 0xffffffff
                                  else struct.pack('>I4s', size, b'free'))
                source.seek(destination.tell())
                copy_bytes(source, destination, end - source.tell())
                destination.write(replacement)
            shutil.copyfileobj(source, destination, 1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())


def read_location(path):
    """Read back the location key from a written QuickTime container."""
    def search(data):
        for kind, payload, raw in boxes(data):
            if kind == b'udta':
                result = search(payload)
                if result is not None:
                    return result
            if kind != b'meta' or not is_mdta(payload):
                continue
            prefix, children = meta_parts(payload)
            keys = next(p for k, p, raw in children if k == b'keys')
            index = next((i + 1 for i, (k, p, raw) in enumerate(boxes(keys[8:]))
                          if k == b'mdta' and p == LOCATION_KEY), None)
            if index is None:
                continue
            items = next(p for k, p, raw in children if k == b'ilst')
            for k, p, raw in boxes(items):
                if k != struct.pack('>I', index):
                    continue
                for item_kind, content, raw in boxes(p):
                    if item_kind == b'data' and content[:8] == struct.pack('>II', 1, 0):
                        return content[8:].decode('ascii')
        return None
    with open(path, 'rb') as file:
        file.seek(0, os.SEEK_END)
        header = InsvHeader.read(file, file.tell())
        if header is None:
            raise ValueError('No INSV trailer found')
        position = 0
        while position < header.metadata_pos:
            file.seek(position)
            size, kind = struct.unpack('>I4s', file.read(8))
            box_header = 8
            if size == 1:
                size = struct.unpack('>Q', file.read(8))[0]
                box_header = 16
            if size < box_header or position + size > header.metadata_pos:
                raise ValueError('Invalid QuickTime container')
            if kind == b'moov':
                if size > 64 * 1024 * 1024:
                    raise ValueError('Movie metadata is too large')
                return search(file.read(size - box_header))
            position += size
    return None
