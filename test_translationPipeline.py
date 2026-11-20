"""A több lépéses fordítás és a folytatás tesztjei, valódi API-költség nélkül."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from seriesMemory import DEFAULT_MEMORY_PATH, load_series_memory
from subtitleApi import cache_configuration
from test_subtitleTranslation import blocks, keep_all
import subtitleTranslation as t


def response(text):
    return {'id': 'resp-test', 'status': 'completed',
            'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}],
            'usage': {'input_tokens': 1200, 'output_tokens': 100, 'total_tokens': 1300,
                      'input_tokens_details': {'cached_tokens': 1024, 'cache_write_tokens': 0}}}


class TranslationPipelineTests(unittest.TestCase):
    def translator(self, **kwargs):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-secret'}):
            return t.openai_translator(model='gpt-6.2-astra', **kwargs)

    def test_verified_memory_has_160_word_summary_and_known_relationships(self):
        memory = load_series_memory()
        self.assertEqual(memory['known_through_episode'], 24)
        self.assertTrue(150 <= len(memory['story_summary'].split()) <= 250)
        self.assertEqual(memory['nicknames']['denizkızı'], 'sellőlány')
        self.assertIn('Teoman Akkaya', memory['relationships'][0]['names'])
        self.assertEqual(memory['status'], 'ready')

    def test_invalid_summary_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'memory.json'
            memory = load_series_memory()
            for summary in ('', 'túl rövid'):
                memory['story_summary'] = summary
                path.write_text(json.dumps(memory))
                with self.assertRaises(ValueError):
                    load_series_memory(path)

    def test_cache_settings_follow_model_family(self):
        modern, explicit = cache_configuration('gpt-6.2-astra')
        self.assertTrue(explicit)
        self.assertEqual(modern['prompt_cache_options'], {'mode': 'explicit', 'ttl': '30m'})
        self.assertEqual(cache_configuration('gpt-4.1')[0], {})
        self.assertEqual(cache_configuration('gpt-4.1', '24h')[0], {'prompt_cache_retention': '24h'})
        for model, policy in (('gpt-6.2-astra', '24h'), ('gpt-4.1', '30m')):
            with self.assertRaises(ValueError):
                cache_configuration(model, policy)

    def test_api_has_stable_prefix_and_excluded_lookahead(self):
        translator = self.translator()
        source = blocks(6)
        with patch('requests.post') as post:
            post.return_value.json.return_value = response(t.format_subtitle(keep_all(source[:1], context=[], start_number=1)))
            translator(source[:1], lookahead=source[1:6])
            first = post.call_args.kwargs['json']
            post.return_value.json.return_value = response(t.format_subtitle(keep_all(source[1:2], context=[], start_number=2)))
            translator(source[1:2], start_number=2)
            second = post.call_args.kwargs['json']
            self.assertEqual(first['input'][0], second['input'][0])
            self.assertEqual(first['input'][0]['content'][0]['prompt_cache_breakpoint'], {'mode': 'explicit'})
            prompt = first['input'][1]['content']
            self.assertIn('Ezeket most ne fordítsd le.', prompt)
            self.assertIn(t.format_subtitle(source[1:6]), prompt)
            self.assertNotIn('instructions', first)

    def test_omitted_speech_restored_and_sound_omission_audited(self):
        translator = self.translator()
        source = blocks(3)
        original_translation = [replace(source[0], number='10', text='Szia')]
        decisions = {'decisions': [
            {'source_index': 1, 'action': 'keep', 'reason': 'Beszéd, nem hangjelzés.', 'translation': 'Ne menj!'},
            {'source_index': 2, 'action': 'omit', 'reason': 'Csak zene.', 'translation': ''}]}
        with patch.object(translator, 'request', return_value=json.dumps(decisions)) as request:
            result, audits = translator.refine_batch(source, original_translation, context=[], lookahead=[], start_number=10)
            self.assertEqual([b.number for b in result], ['10', '11'])
            self.assertEqual(result[1].text, 'Ne menj!')
            self.assertEqual(result[1].timing, source[1].timing)
            self.assertEqual([a['action'] for a in audits], ['keep', 'omit'])
            self.assertEqual(request.call_args.args[0], 'review_omissions')

    def test_uncertain_or_missing_omission_decision_is_rejected(self):
        translator = self.translator()
        decisions = [[], [{'source_index': 0, 'action': 'uncertain', 'reason': 'Nem biztos.', 'translation': ''}]]
        for rows in decisions:
            with self.subTest(rows=rows), patch.object(translator, 'request', return_value=json.dumps({'decisions': rows})):
                with self.assertRaises(RuntimeError):
                    translator.refine_batch(blocks(1), [], context=[], lookahead=[], start_number=1)

    def test_only_problematic_blocks_are_repaired(self):
        translator = self.translator()
        source = blocks(3)
        translated = keep_all(source, context=[], start_number=1)
        translated[1] = replace(translated[1], text='x' * 50)
        repair = replace(translated[1], text='Rövid.')
        with patch.object(translator, 'request', return_value=t.format_subtitle([repair])) as request:
            result, audits = translator.refine_batch(source, translated, context=[], lookahead=[], start_number=1)
            self.assertEqual(result, [translated[0], repair, translated[2]])
            self.assertEqual(audits, [])
            self.assertEqual(request.call_args.args[0], 'repair_readability')
            prompt = request.call_args.args[1]
            target = prompt.split('JAVÍTANDÓ:\n')[1].split('\nMÉRÉSEK:')[0]
            self.assertEqual(t.parse_subtitle(target), [translated[1]])
            self.assertIn('KÖRNYEZŐ TÖRÖK–MAGYAR PÁROK', prompt)

    def test_repair_cannot_drop_or_retime_blocks(self):
        translator = self.translator()
        source = blocks(1)
        translated = [replace(source[0], text='x' * 50)]
        wrong = replace(translated[0], timing='00:01:00,000 --> 00:01:01,000')
        with patch.object(translator, 'request', return_value=t.format_subtitle([wrong])):
            with self.assertRaises(RuntimeError):
                translator.refine_batch(source, translated, context=[], lookahead=[], start_number=1)

    def test_resume_reuses_completed_batch_and_restores_paired_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, destination = Path(tmp) / 'tr.srt', Path(tmp) / 'hu.srt'
            original = blocks(201)
            source.write_text(t.format_subtitle(original))
            first = MagicMock(side_effect=[keep_all(original[:100], context=[], start_number=1), RuntimeError('network')])
            with self.assertRaises(RuntimeError):
                t.translate_subtitle(source=source, destination=destination, translator=first, checkpoint_key='v1')
            self.assertFalse(destination.exists())
            resumed = MagicMock(side_effect=keep_all)
            t.translate_subtitle(source=source, destination=destination, translator=resumed, checkpoint_key='v1')
            self.assertEqual([len(c.args[0]) for c in resumed.call_args_list], [100, 1])
            self.assertEqual(resumed.call_args_list[0].kwargs['start_number'], 101)
            self.assertEqual(resumed.call_args_list[0].kwargs['context'][0].source, original[90])
            self.assertEqual(len(t.load_subtitle(destination)), 201)

    def test_initial_translation_saved_when_refinement_fails(self):
        class FakeTranslator:
            checkpoint_identity = {'version': 1}
            fail = True
            calls = 0
            def __call__(self, batch, **kwargs):
                self.calls += 1
                return keep_all(batch, **kwargs)
            def refine_batch(self, batch, result, **kwargs):
                if self.fail:
                    raise RuntimeError('review failed')
                return result, []
        translator = FakeTranslator()
        with tempfile.TemporaryDirectory() as tmp:
            source, destination = Path(tmp) / 'tr.srt', Path(tmp) / 'hu.srt'
            source.write_text(t.format_subtitle(blocks(2)))
            with self.assertRaises(RuntimeError):
                t.translate_subtitle(source=source, destination=destination, translator=translator)
            translator.fail = False
            t.translate_subtitle(source=source, destination=destination, translator=translator)
            self.assertEqual(translator.calls, 1)

    def test_changed_memory_or_model_changes_checkpoint_identity(self):
        first = self.translator()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'memory.json'
            memory = load_series_memory()
            memory['notes'] += ' Kiegészítés.'
            path.write_text(json.dumps(memory))
            second = self.translator(memory_path=path)
            self.assertNotEqual(first.checkpoint_identity, second.checkpoint_identity)
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'fake'}):
            other = t.openai_translator(model='gpt-4.1')
        self.assertNotEqual(first.checkpoint_identity, other.checkpoint_identity)

    def test_response_reuse_logs_cached_tokens_without_keys_or_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            translator = self.translator()
            log = Path(tmp) / 'usage.jsonl'
            translator.configure_storage(tmp, log)
            with patch('requests.post') as post:
                post.return_value.json.return_value = response('Szia')
                self.assertEqual(translator.request('test', 'sensitive-prompt'), 'Szia')
                self.assertEqual(translator.request('test', 'sensitive-prompt'), 'Szia')
                self.assertEqual(post.call_count, 1)
            text = log.read_text()
            self.assertNotIn('test-secret', text)
            self.assertNotIn('sensitive-prompt', text)
            self.assertNotIn('Szia', text)
            events = [json.loads(line) for line in text.splitlines()]
            self.assertEqual(events[0]['cached_tokens'], 1024)
            self.assertTrue(events[0]['cache_hit'])
            self.assertEqual(events[0]['input_tokens'], 1200)
            self.assertGreaterEqual(events[0]['elapsed_seconds'], 0)
            self.assertEqual(events[1]['event'], 'local_response_reused')

    def test_corrupt_checkpoint_fails_without_paying_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, destination = Path(tmp) / 'tr.srt', Path(tmp) / 'hu.srt'
            source.write_text(t.format_subtitle(blocks(2)))
            first = MagicMock(side_effect=[keep_all(blocks(1), context=[], start_number=1), RuntimeError('failure')])
            with self.assertRaises(RuntimeError):
                t.translate_subtitle(source=source, destination=destination, translator=first, batch_size=1, checkpoint_key='v1')
            path = next(destination.with_suffix('.checkpoints').rglob('*.complete.json'))
            data = json.loads(path.read_text())
            data['body']['srt'] += '\ncorrupt'
            path.write_text(json.dumps(data))
            translator = MagicMock()
            with self.assertRaises(ValueError):
                t.translate_subtitle(source=source, destination=destination, translator=translator, batch_size=1, checkpoint_key='v1')
            translator.assert_not_called()

    def test_full_pipeline_and_second_run_use_saved_batches(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, destination = Path(tmp) / 'tr.srt', Path(tmp) / 'hu.srt'
            original = blocks(3)
            source.write_text(t.format_subtitle(original))
            initial = [replace(original[0], text='x' * 50)]
            decisions = {'decisions': [
                {'source_index': 1, 'action': 'keep', 'reason': 'Elhangzó beszéd.', 'translation': 'Ne menj!'},
                {'source_index': 2, 'action': 'omit', 'reason': 'Csak zene.', 'translation': ''}]}
            repaired = [replace(initial[0], text='Maradj!')]
            with patch('requests.post') as post:
                post.return_value.json.side_effect = [response(t.format_subtitle(initial)),
                    response(json.dumps(decisions)), response(t.format_subtitle(repaired))]
                t.translate_subtitle(source=source, destination=destination, translator=self.translator())
                self.assertEqual(post.call_count, 3)
                self.assertEqual([b.text for b in t.load_subtitle(destination)], ['Maradj!', 'Ne menj!'])
                report = json.loads(destination.with_suffix('.review.json').read_text())
                self.assertEqual([a['action'] for a in report['omission_audits']], ['keep', 'omit'])
                self.assertEqual(report['readability_warning_blocks'], 0)
                destination.unlink()
                destination.with_suffix('.review.json').unlink()
                t.translate_subtitle(source=source, destination=destination, translator=self.translator())
                self.assertEqual(post.call_count, 3)
            events = [json.loads(line) for line in destination.with_suffix('.usage.jsonl').read_text().splitlines()]
            self.assertEqual([e['task'] for e in events if e['event'] == 'api_response'],
                             ['translate', 'review_omissions', 'repair_readability'])
            self.assertTrue(any(e.get('checkpoint_reused') for e in events))

    def test_failed_entrypoint_logs_elapsed_time_without_raw_error(self):
        with tempfile.TemporaryDirectory() as tmp, patch('subtitleTranslation.openai_translator', side_effect=RuntimeError('sensitive-error')), patch('sys.stderr'):
            source = Path(tmp) / 'Daha17_25_1080p.tr.srt'
            source.write_text(t.format_subtitle(blocks(1)))
            self.assertIsNone(t.translate_episode_subtitle(episode=25, directory=tmp, model='test'))
            text = (Path(tmp) / 'Daha17_25_1080p.hu.usage.jsonl').read_text()
            event = json.loads(text)
            self.assertEqual(event['event'], 'run_failed')
            self.assertEqual(event['error_type'], 'RuntimeError')
            self.assertGreaterEqual(event['elapsed_seconds'], 0)
            self.assertNotIn('sensitive-error', text)
