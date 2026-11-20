"""Felirat-időzítés, olvashatóság és kihagyások ellenőrzése API-hívás nélkül.

A kihagyott blokkokat felülvizsgálandóként jelzi; tartalmuk indokoltságát nem
minősíti automatikusan. A 17 CPS, két sor és 42 karakter/sor irányérték.
"""

from html import unescape
import re


def duration_seconds(timing):
    match = re.fullmatch(
        r'(\d{2}):([0-5]\d):([0-5]\d),(\d{3}) --> '
        r'(\d{2}):([0-5]\d):([0-5]\d),(\d{3})(?: .*)?', timing)
    if match is None:
        raise ValueError(f'Hibás SRT időzítés: {timing}')
    h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, match.groups())
    duration_ms = ((h2 - h1) * 3600 + (m2 - m1) * 60 + s2 - s1) * 1000 + ms2 - ms1
    if duration_ms <= 0:
        raise ValueError(f'A megjelenési idő nem pozitív: {timing}')
    return duration_ms / 1000


def readability(block):
    """Látható karakterek: szóközökkel, sortörések és SRT HTML-tagek nélkül."""
    duration = duration_seconds(block.timing)
    lines = unescape(re.sub(r'<[^>]*>', '', block.text)).splitlines()
    lengths = [len(line) for line in lines]
    characters = sum(lengths)
    cps = characters / duration
    warnings = []
    if cps > 17:
        warnings.append('reading_speed_above_17_cps')
    if len(lines) > 2:
        warnings.append('more_than_two_lines')
    if any(length > 42 for length in lengths):
        warnings.append('line_above_42_characters')
    return {'number': block.number, 'timing': block.timing, 'text': block.text,
            'duration_seconds': duration, 'characters': characters,
            'characters_per_second': cps, 'line_lengths': lengths, 'warnings': warnings}


def quality_report(source, translated):
    """Listázza a kimaradt forrásblokkokat és méri az összes magyar blokkot."""
    cursor = 0
    omissions = []
    for block in translated:
        while cursor < len(source) and source[cursor].timing != block.timing:
            original = source[cursor]
            omissions.append({'source_position': cursor + 1, 'number': original.number,
                              'timing': original.timing, 'text': original.text,
                              'status': 'needs_content_review'})
            cursor += 1
        if cursor == len(source):
            raise ValueError('A magyar időzítés nem illeszkedik a forráshoz.')
        cursor += 1
    for position in range(cursor, len(source)):
        original = source[position]
        omissions.append({'source_position': position + 1, 'number': original.number,
                          'timing': original.timing, 'text': original.text,
                          'status': 'needs_content_review'})
    metrics = [readability(block) for block in translated]
    warning_count = sum(bool(metric['warnings']) for metric in metrics)
    return {
        'status': 'needs_review' if omissions or warning_count else 'no_structural_or_readability_warnings',
        'semantic_completeness_verified': False,
        'source_blocks': len(source), 'translated_blocks': len(translated),
        'omitted_blocks': omissions, 'readability_warning_blocks': warning_count,
        'readability': metrics,
    }
