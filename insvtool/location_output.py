"""Readable location reports."""

def format_video_time(seconds):
    if seconds is None:
        return 'unknown (video timing metadata unavailable)'
    milliseconds = round(abs(seconds) * 1000)
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    secs, millis = divmod(remainder, 1000)
    return f'{"-" if seconds < 0 else ""}{hours}:{minutes:02d}:{secs:02d}.{millis:03d}'


def format_location(entry):
    lines = [entry['path']]
    if 'latitude' in entry:
        lines.extend([
            f"  Video time: {format_video_time(entry['videoTime'])}",
            f"  GPS date/time: {entry['gpsDateTime']}",
            f"  Coordinates: {entry['latitude']:.8f}, {entry['longitude']:.8f}",
            f"  Location: {entry.get('locationName', 'unavailable')}",
            f"  Map: {entry['mapUrl']}",
        ])
    if entry.get('modified'):
        lines.append(f"  Written: {entry.get('output', entry['path'])}")
    if 'error' in entry:
        lines.append(f"  Error: {entry['error']}")
    return '\n'.join(lines)
