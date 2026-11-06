import re
import unicodedata
from collections import defaultdict
from math import floor
from statistics import median

from app.common.comparison_options import ComparisonOptions


def collect_raw_chars(raw_dict, page_num, excluded_bounds=None):
    chars = []
    for block_index, block in enumerate(raw_dict.get('blocks', [])):
        if excluded_bounds is not None and block.get('type') != 0:
            continue
        for line_index, line in enumerate(block.get('lines', [])):
            for span_index, span in enumerate(line.get('spans', [])):
                for char_index, char in enumerate(span.get('chars', [])):
                    bbox = char['bbox']
                    if excluded_bounds is not None:
                        top, bottom = excluded_bounds
                        if bbox[3] <= top or bbox[1] >= bottom:
                            continue
                    chars.append({
                        'char': unicodedata.normalize('NFC', char['c']),
                        'source_char': char['c'],
                        'line_id': (page_num, block_index, line_index),
                        'source_id': (page_num, block_index, line_index, span_index, char_index),
                        'origin': char.get('origin'),
                        'font_size': span.get('size'),
                        'line_dir': tuple(line.get('dir', (1.0, 0.0))),
                        'wmode': line.get('wmode', 0),
                        'bbox': bbox, 'y': bbox[1], 'x': bbox[0], 'page': page_num,
                    })
    return chars


def normalize_raw_chars(raw_chars, page_aware=False, options=None):
    options = options or ComparisonOptions()
    if options.mode != 'body':
        return _normalize_with_options(raw_chars, page_aware, options)
    # Keep the legacy path unchanged, including whitelist and word IDs.
    if not raw_chars:
        return [], ''
    raw_chars.sort(key=(lambda char: (char['page'], char['y'])) if page_aware
                   else (lambda char: char['y']))
    grouped = []
    curr = [raw_chars[0]]
    for i in range(1, len(raw_chars)):
        if page_aware:
            same_line = (raw_chars[i]['page'] == curr[-1]['page']
                         and abs(raw_chars[i]['y'] - curr[-1]['y']) < 5.0)
        else:
            same_line = raw_chars[i]['y'] - curr[-1]['y'] < 5.0
        if same_line:
            curr.append(raw_chars[i])
        else:
            grouped.append(curr)
            curr = [raw_chars[i]]
    grouped.append(curr)

    final_norm = []
    raw_lines = []
    word_counter = 0
    for line in grouped:
        line.sort(key=lambda char: char['x'])
        line_str_raw = []
        word_counter += 1
        page_num = line[0]['page']
        for i, char in enumerate(line):
            line_str_raw.append(char['char'])
            if i > 0 and (line[i - 1]['char'].strip() == ''
                          or abs(char['x'] - line[i - 1]['bbox'][2]) > 2.5):
                word_counter += 1
            clean_char = char['char'].lower().strip()
            if not re.match(r'[가-힣a-z0-9.,?!;:()\-\[\]{}\'"]', clean_char):
                continue
            if not final_norm or not (clean_char == final_norm[-1]['char']
                                      and abs(char['x'] - final_norm[-1]['x']) < 2.5):
                final_norm.append({
                    'char': clean_char, 'bbox': char['bbox'], 'x': char['x'],
                    'y': char['y'], 'page': page_num, 'word_id': word_counter,
                })
        raw_lines.append(''.join(line_str_raw))
    return final_norm, '\n'.join(raw_lines)


def _source(glyph):
    return glyph.get('source_char', glyph['char'])


def _anchor(glyph):
    # Font ascenders change bbox.y0 even on the same baseline. Prefer the
    # extraction origin; callers without metadata can use the box bottom.
    return glyph.get('origin') or (glyph['bbox'][0], glyph['bbox'][3])


def _horizontal(glyph):
    dx, dy = glyph.get('line_dir', (1.0, 0.0))
    return glyph.get('wmode', 0) == 0 and dx >= 0.999 and abs(dy) <= 0.001


def _fragment(chars):
    return {
        'chars': list(chars),
        'page': chars[0]['page'],
        'horizontal': all(_horizontal(char) for char in chars),
        'baselines': [median(_anchor(char)[1] for char in chars)],
        'size': median(char.get('font_size') or max(0.1, char['bbox'][3] - char['bbox'][1])
                       for char in chars),
        'bbox': (min(char['bbox'][0] for char in chars), min(char['bbox'][1] for char in chars),
                 max(char['bbox'][2] for char in chars), max(char['bbox'][3] for char in chars)),
    }


def _can_merge_line(left, right):
    if left['page'] != right['page'] or not left['horizontal'] or not right['horizontal']:
        return False
    tolerance = min(2.0, max(0.4, 0.15 * min(left['size'], right['size'])))
    baselines = left['baselines'] + right['baselines']
    # Bound the whole cluster, so small offsets cannot chain adjacent rows.
    if max(baselines) - min(baselines) > tolerance:
        return False
    a, b = left['bbox'], right['bbox']
    overlap = min(a[3], b[3]) - max(a[1], b[1])
    if overlap < 0.5 * min(a[3] - a[1], b[3] - b[1]):
        return False
    # Nearby fragments and overlays can belong to one visual line. A large
    # gutter must not merge separate columns/cells into the same line.
    gap = max(a[0], b[0]) - min(a[2], b[2])
    return gap <= max(3.0, 1.5 * min(left['size'], right['size']))


def _reconstruct_lines(raw_chars):
    line_map = defaultdict(list)
    for index, char in enumerate(raw_chars):
        # Pages are always separate, including calls without page_aware=True.
        key = (char['page'], char.get('line_id', ('glyph', index)))
        line_map[key].append(char)
    fragments = [_fragment(chars) for chars in line_map.values()]
    fragments.sort(key=lambda part: (part['page'], part['baselines'][0], part['bbox'][0]))
    pages = defaultdict(list)
    for fragment in fragments:
        candidates = pages[fragment['page']]
        matches = [line for line in candidates if _can_merge_line(line, fragment)]
        if not matches:
            candidates.append(fragment)
            continue
        target = min(matches, key=lambda line: (
            abs(median(line['baselines']) - fragment['baselines'][0]),
            abs(line['bbox'][0] - fragment['bbox'][0])))
        target['chars'].extend(fragment['chars'])
        target['baselines'].extend(fragment['baselines'])
        a, b = target['bbox'], fragment['bbox']
        target['bbox'] = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
        # A later body span can bridge several separately painted overlays.
        # Absorb all of them, rather than leaving an earlier fragment behind.
        while True:
            adjacent = next((line for line in candidates
                             if line is not target and _can_merge_line(target, line)), None)
            if adjacent is None:
                break
            target['chars'].extend(adjacent['chars'])
            target['baselines'].extend(adjacent['baselines'])
            a, b = target['bbox'], adjacent['bbox']
            target['bbox'] = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
            candidates.remove(adjacent)
    lines = [line for page in pages.values() for line in page]
    lines.sort(key=lambda line: (line['page'], median(line['baselines']), line['bbox'][0]))
    return [sorted(line['chars'], key=lambda char: char['bbox'][0])
            if line['horizontal'] else line['chars'] for line in lines]


def _same_printed_glyph(left, right):
    if (left['page'] != right['page'] or _source(left) != _source(right)
            or left.get('line_dir', (1.0, 0.0)) != right.get('line_dir', (1.0, 0.0))
            or left.get('wmode', 0) != right.get('wmode', 0)):
        return False
    a, b = left['bbox'], right['bbox']
    aw, ah, bw, bh = a[2] - a[0], a[3] - a[1], b[2] - b[0], b[3] - b[1]
    # Zero-width combining/format characters are content, not overprints.
    if min(aw, ah, bw, bh) <= 0:
        return False
    tolerance = min(2.0, 0.15 * min(ah, bh))
    if any(abs(x - y) > tolerance for x, y in zip(_anchor(left), _anchor(right))):
        return False
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return intersection / (aw * ah + bw * bh - intersection) >= 0.70


def _deduplicate_glyphs(line):
    # A spatial index keeps repeated letters on long lines from turning this
    # into an all-pairs comparison. Only identical, overlapping glyphs qualify.
    buckets = defaultdict(list)
    kept = []
    for glyph in line:
        x, y = _anchor(glyph)
        col, row = floor(x / 2.0), floor(y / 2.0)
        source = _source(glyph)
        duplicate = any(
            _same_printed_glyph(earlier, glyph)
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            for earlier in buckets[(source, col + dx, row + dy)]
        )
        if not duplicate:
            kept.append(glyph)
            buckets[(source, col, row)].append(glyph)
    return kept


def _normalize_with_options(raw_chars, page_aware, options):
    if not raw_chars:
        return [], ''
    lines = _reconstruct_lines(raw_chars)

    normalized, raw_lines = [], []
    word_id = 0
    previous_line = None
    for line in lines:
        # The Raw view retains all extracted characters (including overprints)
        # in reconstructed reading order, before comparison filters/deduplication.
        raw_lines.append(''.join(_source(char) for char in line))
        line = _deduplicate_glyphs(line)
        if previous_line is not None and not options.ignore_line_breaks:
            word_id += 1
            previous = previous_line[-1]
            x0, y0, x1, y1 = previous['bbox']
            # A PDF has no newline glyph. Anchor its marker at the preceding line end.
            normalized.append({**previous, 'char': '\n', 'source_char': '\n',
                               'bbox': (max(x0, x1 - 2), y0, x1, y1),
                               'word_id': word_id, 'synthetic': True})
        word_id += 1
        for index, glyph in enumerate(line):
            source = glyph.get('source_char', glyph['char'])
            if index and (line[index - 1].get('source_char', line[index - 1]['char']).isspace()
                          or abs(glyph['x'] - line[index - 1]['bbox'][2]) > 2.5):
                word_id += 1
            for character in source:
                is_newline = character in '\r\n\u2028\u2029'
                if is_newline and options.ignore_line_breaks:
                    continue
                if character.isspace() and not is_newline and options.ignore_spaces:
                    continue
                if options.ignore_symbols and unicodedata.category(character)[0] in ('P', 'S'):
                    continue
                value = character.lower() if options.ignore_case else character
                # One record per code point keeps diff offsets and highlight positions aligned.
                for codepoint in value:
                    normalized.append({**glyph, 'char': codepoint,
                                       'source_char': source, 'word_id': word_id})
        previous_line = line
    return normalized, '\n'.join(raw_lines)
