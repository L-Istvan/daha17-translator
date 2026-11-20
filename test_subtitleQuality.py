import unittest

from subtitleQuality import duration_seconds, quality_report, readability
from subtitleTranslation import SubtitleBlock


class SubtitleQualityTests(unittest.TestCase):
    def test_duration_crosses_minute_and_hour_boundaries(self):
        self.assertEqual(duration_seconds('00:59:59,750 --> 01:00:01,250'), 1.5)

    def test_invalid_nonpositive_timing_is_rejected(self):
        for timing in ('00:00:02,000 --> 00:00:01,000',
                       '00:00:01,000 --> 00:00:01,000',
                       '00:60:00,000 --> 01:00:01,000',
                       '00:00:60,000 --> 00:01:02,000'):
            with self.subTest(timing=timing), self.assertRaises(ValueError):
                duration_seconds(timing)

    def test_cps_includes_spaces_and_excludes_markup_and_newlines(self):
        block = SubtitleBlock('1', '00:00:00,000 --> 00:00:02,000', '<i>Ár &amp; víz</i>\nŐ')
        result = readability(block)
        self.assertEqual(result['line_lengths'], [8, 1])
        self.assertEqual(result['characters'], 9)
        self.assertEqual(result['characters_per_second'], 4.5)
        self.assertEqual(result['warnings'], [])

    def test_readability_limits_are_warnings(self):
        block = SubtitleBlock('1', '00:00:00,000 --> 00:00:01,000', 'a' * 43 + '\nb\nc')
        self.assertEqual(readability(block)['warnings'], [
            'reading_speed_above_17_cps', 'more_than_two_lines', 'line_above_42_characters'])
        exact = SubtitleBlock('2', '00:00:01,000 --> 00:00:02,000', 'a' * 17)
        self.assertEqual(readability(exact)['warnings'], [])

    def test_all_omissions_are_flagged_including_possible_dialogue(self):
        source = [SubtitleBlock(str(i), f'00:00:0{i},000 --> 00:00:0{i},900', text)
                  for i, text in enumerate(['Merhaba!', '(Müzik)', 'Gitme!', 'Hayır!'], 1)]
        translated = [SubtitleBlock('1', source[1].timing, 'Zene')]
        report = quality_report(source, translated)
        self.assertEqual([b['number'] for b in report['omitted_blocks']], ['1', '3', '4'])
        self.assertEqual(report['omitted_blocks'][1]['text'], 'Gitme!')
        self.assertEqual(report['status'], 'needs_review')
        self.assertFalse(report['semantic_completeness_verified'])

    def test_empty_translation_reports_every_omission(self):
        source = [SubtitleBlock('1', '00:00:00,000 --> 00:00:01,000', '(Müzik)')]
        report = quality_report(source, [])
        self.assertEqual(len(report['omitted_blocks']), 1)
        self.assertEqual(report['status'], 'needs_review')
