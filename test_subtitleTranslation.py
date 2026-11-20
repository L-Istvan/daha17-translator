import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import subtitleTranslation as t


def blocks(count):
    return [t.SubtitleBlock(str(i + 1), f'00:{i // 60:02d}:{i % 60:02d},000 --> 00:{i // 60:02d}:{i % 60:02d},900', f'Merhaba {i}') for i in range(count)]


def keep_all(batch, *, context, start_number, lookahead=()):
    return [t.SubtitleBlock(str(i), b.timing, 'Magyar\nSzöveg') for i, b in enumerate(batch, start_number)]


class SubtitleTranslationTests(unittest.TestCase):
    def test_201_blocks_batches_preserve_timings_and_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, destination = Path(tmp) / 'tr.srt', Path(tmp) / 'hu.srt'
            original = blocks(201)
            source.write_text('\ufeff' + t.format_subtitle(original).replace('\n', '\r\n'), encoding='utf-8')
            translator = MagicMock(side_effect=keep_all)
            t.translate_subtitle(source=source, destination=destination, translator=translator)
            self.assertEqual([len(c.args[0]) for c in translator.call_args_list], [100, 100, 1])
            result = t.load_subtitle(destination)
            self.assertEqual([(b.number, b.timing) for b in result], [(b.number, b.timing) for b in original])
            self.assertEqual(translator.call_args_list[0].kwargs, {'context': [], 'lookahead': original[100:105], 'start_number': 1})
            self.assertEqual(translator.call_args_list[1].kwargs, {'context': [t.TranslationPair(a, b) for a, b in zip(original[90:100], result[90:100])], 'lookahead': original[200:201], 'start_number': 101})
            self.assertEqual(translator.call_args_list[2].kwargs, {'context': [t.TranslationPair(a, b) for a, b in zip(original[190:200], result[190:200])], 'lookahead': [], 'start_number': 201})
            self.assertIn('Merhaba', source.read_text())

    def test_filtering_uses_hungarian_numbering_and_keeps_context_across_empty_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, destination = Path(tmp) / 'tr.srt', Path(tmp) / 'hu.srt'
            original = blocks(6)
            source.write_text(t.format_subtitle(original))
            first = t.SubtitleBlock('325', original[1].timing, 'Gyere, hozzuk el a testvéredet.')
            last = t.SubtitleBlock('326', original[5].timing, 'Folytatás')
            translator = MagicMock(side_effect=[[first], [], [last]])
            t.translate_subtitle(source=source, destination=destination, translator=translator, batch_size=2, start_number=325, context_blocks=5)
            self.assertEqual(t.load_subtitle(destination), [first, last])
            report = json.loads(destination.with_suffix('.review.json').read_text())
            self.assertEqual(report['status'], 'needs_review')
            self.assertEqual([b['number'] for b in report['omitted_blocks']], ['1', '3', '4', '5'])
            self.assertEqual(len(report['readability']), 2)
            self.assertFalse(report['semantic_completeness_verified'])
            self.assertEqual(translator.call_args_list[1].kwargs, {'context': [t.TranslationPair(original[1], first)], 'lookahead': original[4:6], 'start_number': 326})
            self.assertEqual(translator.call_args_list[2].kwargs, {'context': [t.TranslationPair(original[1], first)], 'lookahead': [], 'start_number': 326})

    def test_invalid_translation_does_not_create_file(self):
        original = blocks(2)
        bad_results = [None, ['text'], [t.SubtitleBlock('2', original[0].timing, 'wrong number')],
                       [t.SubtitleBlock('1', '00:59:00,000 --> 00:59:01,000', 'changed')],
                       [t.SubtitleBlock('1', original[1].timing, 'one'), t.SubtitleBlock('2', original[0].timing, 'reversed')],
                       [t.SubtitleBlock('1', original[0].timing, 'one'), t.SubtitleBlock('2', original[0].timing, 'repeated')]]
        for result in bad_results:
            with self.subTest(result=result), tempfile.TemporaryDirectory() as tmp:
                source, destination = Path(tmp) / 'tr.srt', Path(tmp) / 'hu.srt'
                source.write_text(t.format_subtitle(original))
                with self.assertRaises(ValueError):
                    t.translate_subtitle(source=source, destination=destination, translator=MagicMock(return_value=result))
                self.assertFalse(destination.exists())

    def test_failed_second_batch_creates_no_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, destination = Path(tmp) / 'tr.srt', Path(tmp) / 'hu.srt'
            source.write_text(t.format_subtitle(blocks(101)))
            translator = MagicMock(side_effect=[keep_all(blocks(100), context=[], start_number=1), RuntimeError('failure')])
            with self.assertRaises(RuntimeError):
                t.translate_subtitle(source=source, destination=destination, translator=translator)
            self.assertFalse(destination.exists())

    def test_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'hu.srt'
            destination.write_text('existing')
            translator = MagicMock()
            with self.assertRaises(FileExistsError):
                t.translate_subtitle(source='missing', destination=destination, translator=translator)
            translator.assert_not_called()
            self.assertEqual(destination.read_text(), 'existing')

    def test_invalid_srt_and_parameters(self):
        for text in ('', 'not SRT', '1\nwrong timing\ntext', '```srt\n1\n00:00:00,000 --> 00:00:01,000\nHi\n```'):
            with self.assertRaises(ValueError):
                t.parse_subtitle(text)
        for size in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                list(t.subtitle_batches([], size))
            for param in ('start_number', 'context_blocks'):
                with self.assertRaises(ValueError):
                    t.translate_subtitle(source='missing', destination='unused', translator=MagicMock(), **{param: size})

    def test_existing_report_is_not_overwritten_and_prevents_api_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'hu.srt'
            report = destination.with_suffix('.review.json')
            report.write_text('existing')
            translator = MagicMock()
            with self.assertRaises(FileExistsError):
                t.translate_subtitle(source='missing', destination=destination, translator=translator)
            translator.assert_not_called()
            self.assertEqual(report.read_text(), 'existing')
            self.assertFalse(destination.exists())

    def test_missing_key_does_not_call_api(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}), patch('requests.post') as post:
            with self.assertRaisesRegex(ValueError, 'OPENAI_API_KEY'):
                t.openai_translator(model='test')
            post.assert_not_called()

    def test_api_sends_instructions_context_timing_and_hungarian_start_number(self):
        context = [t.TranslationPair(t.SubtitleBlock('399', '00:00:01,000 --> 00:00:02,000', 'Kardeşini alalım.'), t.SubtitleBlock('325', '00:00:01,000 --> 00:00:02,000', 'Gyere, hozzuk el a testvéredet.'))]
        batch = [t.SubtitleBlock('400', '00:00:03,000 --> 00:00:04,000', '(Radyo kadın ses) Serhat')]
        result = [t.SubtitleBlock('326', batch[0].timing, 'Serhat')]
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'fake'}), patch('requests.post') as post:
            post.return_value.json.return_value = {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': t.format_subtitle(result)}]}]}
            self.assertEqual(t.openai_translator(model='test')(batch, context=context, start_number=326), result)
            body = post.call_args.kwargs['json']
            self.assertFalse(body['store'])
            prefix = body['input'][0]['content'][0]['text']
            self.assertIn(t.TRANSLATION_INSTRUCTIONS, prefix)
            self.assertIn('ÁLLANDÓ SOROZATMEMÓRIA', prefix)
            self.assertIn('Aras Öztürk', prefix)
            prompt = body['input'][1]['content']
            self.assertIn(t.format_subtitle([context[0].target]), prompt)
            self.assertIn(t.format_subtitle([context[0].source]), prompt)
            self.assertIn(t.format_subtitle(batch), prompt)
            self.assertIn('kezdősorszáma: 326', prompt)
            self.assertIn('utolsó sorszáma: 325', prompt)
            self.assertNotIn('text', body)  # A válasz SRT, nem JSON.

    def test_api_rejects_incomplete_refused_missing_and_non_srt_outputs(self):
        for payload in ({'status': 'incomplete'}, {'status': 'completed', 'output': []},
                        {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'refusal'}]}]},
                        {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'Explanation'}]}]}):
            with self.subTest(payload=payload), patch.dict('os.environ', {'OPENAI_API_KEY': 'fake'}), patch('requests.post') as post:
                post.return_value.json.return_value = payload
                with self.assertRaises(RuntimeError):
                    t.openai_translator(model='test')(blocks(1))

    def test_api_accepts_explicit_empty_text_when_all_blocks_filtered(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'fake'}), patch('requests.post') as post:
            post.return_value.json.return_value = {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': ''}]}]}
            self.assertEqual(t.openai_translator(model='test')(blocks(1)), [])

    def test_api_http_error(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'fake'}), patch('requests.post') as post:
            post.return_value.ok = False
            post.return_value.status_code = 429
            with self.assertRaisesRegex(RuntimeError, 'HTTP 429'):
                t.openai_translator(model='test')(blocks(1))
