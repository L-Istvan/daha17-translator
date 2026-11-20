"""A három fő lépés sorrendje, leállása és újraindítása, hálózat nélkül."""

from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import main


SRT = '1\n00:00:01,000 --> 00:00:02,000\nMerhaba\n'


class PipelineTests(unittest.TestCase):
    def test_steps_run_in_order_with_same_episode_and_test_limit(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            calls = []
            for name in ('download_video', 'download_subtitle', 'translate_episode_subtitle'):
                def success(name=name, **kwargs):
                    calls.append((name, kwargs))
                    return Path(tmp) / name
                stack.enter_context(patch('main.' + name, side_effect=success))
            self.assertEqual(main.run_pipeline(episode=25, directory=tmp), 0)
            self.assertEqual([name for name, _ in calls],
                ['download_video', 'download_subtitle', 'translate_episode_subtitle'])
            self.assertEqual(calls[0][1]['target_episode'], 25)
            self.assertTrue(calls[0][1]['exact_episode'])
            self.assertEqual(calls[1][1]['episode'], 25)
            self.assertEqual(calls[2][1]['episode'], 25)
            self.assertEqual(calls[2][1]['max_batches'], 6)
            self.assertTrue(calls[1][1]['raise_errors'])
            self.assertTrue(calls[2][1]['raise_errors'])

    def test_failure_in_each_step_stops_later_steps_and_logs_timestamp_and_reason(self):
        names = ('download_video', 'download_subtitle', 'translate_episode_subtitle')
        for failing in range(3):
            for exception in (False, True):
                with self.subTest(stage=failing, exception=exception), tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
                    mocks = [stack.enter_context(patch('main.' + name, return_value=Path(tmp) / name)) for name in names]
                    if exception:
                        mocks[failing].side_effect = RuntimeError('Konkrét hiba oka')
                    else:
                        mocks[failing].return_value = None
                    self.assertEqual(main.run_pipeline(directory=tmp), 1)
                    for later in mocks[failing + 1:]:
                        later.assert_not_called()
                    log = (Path(tmp) / 'pipeline.log').read_text()
                    stopped = log.splitlines()[-1]
                    self.assertIn('LEÁLLT', stopped)
                    self.assertIn(f'{failing + 1}.', stopped)
                    self.assertRegex(stopped, r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+(?:01|02):00')
                    if exception:
                        self.assertIn('Konkrét hiba oka', stopped)

    def test_interrupt_is_logged_and_stops_next_steps(self):
        with tempfile.TemporaryDirectory() as tmp, patch('main.download_video', side_effect=KeyboardInterrupt), patch('main.download_subtitle') as subtitle:
            self.assertEqual(main.run_pipeline(directory=tmp), 130)
            subtitle.assert_not_called()
            self.assertIn('Ctrl+C', (Path(tmp) / 'pipeline.log').read_text())

    def test_restart_with_existing_files_never_downloads_or_calls_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'Daha17_25_1080p.mp4').write_bytes(b'video')
            (Path(tmp) / 'Daha17_25_1080p.tr.srt').write_text(SRT)
            (Path(tmp) / 'Daha17_25_1080p.hu.test600.srt').write_text(SRT)
            with patch('requests.get') as get, patch('requests.post') as post, patch('downloader.shutil.which', return_value='/usr/bin/ffmpeg'), patch('downloader.subprocess.run') as execute:
                self.assertEqual(main.run_pipeline(directory=tmp), 0)
                self.assertEqual(main.run_pipeline(directory=tmp), 0)
                get.assert_not_called()
                post.assert_not_called()
                self.assertEqual(execute.call_count, 2)

    def test_unavailable_subtitle_logs_http_error_and_never_translates(self):
        from requests import HTTPError
        with tempfile.TemporaryDirectory() as tmp, patch('main.download_video', return_value=Path(tmp) / 'video.mp4'), patch('requests.get') as get, patch('main.translate_episode_subtitle') as translate:
            get.return_value.raise_for_status.side_effect = HTTPError('404: a felirat nem elérhető')
            self.assertEqual(main.run_pipeline(directory=tmp), 1)
            translate.assert_not_called()
            self.assertIn('404', (Path(tmp) / 'pipeline.log').read_text())
            self.assertFalse((Path(tmp) / 'Daha17_25_1080p.tr.srt').exists())

    def test_bad_existing_subtitle_stops_without_network_or_translation(self):
        with tempfile.TemporaryDirectory() as tmp, patch('main.download_video', return_value=Path(tmp) / 'video.mp4'), patch('requests.get') as get, patch('main.translate_episode_subtitle') as translate:
            (Path(tmp) / 'Daha17_25_1080p.tr.srt').write_text('')
            self.assertEqual(main.run_pipeline(directory=tmp), 1)
            get.assert_not_called()
            translate.assert_not_called()
            self.assertIn('üres', (Path(tmp) / 'pipeline.log').read_text())

    def test_translation_error_reaches_pipeline_log_with_original_reason(self):
        with tempfile.TemporaryDirectory() as tmp, patch('main.download_video', return_value=Path(tmp) / 'video.mp4'), patch('main.download_subtitle', return_value=Path(tmp) / 'subtitle.srt'), patch('subtitleTranslation.openai_translator', side_effect=ValueError('Hiányzik az OPENAI_API_KEY környezeti változó.')):
            (Path(tmp) / 'Daha17_25_1080p.tr.srt').write_text(SRT)
            self.assertEqual(main.run_pipeline(directory=tmp), 1)
            log = (Path(tmp) / 'pipeline.log').read_text()
            self.assertIn('LEÁLLT | 3. Magyar fordítás', log)
            self.assertIn('Hiányzik az OPENAI_API_KEY', log)
