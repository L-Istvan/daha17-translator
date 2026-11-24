"""A három fő lépés sorrendje, leállása és újraindítása, hálózat nélkül."""

from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import main
import videa_uploader
from translationStorage import digest


SRT = '1\n00:00:01,000 --> 00:00:02,000\nMerhaba\n'


class PipelineTests(unittest.TestCase):
    def test_safe_option_is_forwarded_to_downloader(self):
        for options, expected in (({}, False), ({'safe': True}, True)):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as tmp, patch('main.download_video', return_value=None) as download:
                self.assertEqual(main.run_pipeline(directory=tmp, **options), 1)
                self.assertEqual(download.call_args.kwargs['safe'], expected)

    def setUp(self):
        # A gép valódi Videa-adatai ne kerülhessenek teszthívásokba/hibaüzenetekbe.
        environment = patch.dict('os.environ', {
            'VIDEA_EMAIL': '', 'VIDEA_PASSWORD': '', 'VIDEA_SESSION_PATH': '',
        })
        environment.start()
        self.addCleanup(environment.stop)

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
            self.assertNotIn('page_url', calls[0][1])  # A letöltő az adott rész saját linkjét keresi ki.
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
                execute.assert_not_called()
                self.assertEqual(main.run_pipeline(directory=tmp, safe=True), 0)
                execute.assert_called_once()
                get.assert_not_called()
                post.assert_not_called()

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
            self.assertRegex(log, r'LEÁLLT[^\n]*3\. Magyar fordítás')
            self.assertIn('Hiányzik az OPENAI_API_KEY', log)

    def test_upload_is_disabled_during_default_test_run(self):
        with tempfile.TemporaryDirectory() as tmp, patch('main.download_video', return_value='video.mp4'), patch('main.download_subtitle', return_value='tr.srt'), patch('main.translate_episode_subtitle', return_value='hu.test600.srt'), patch('main.upload_video') as upload:
            self.assertEqual(main.run_pipeline(directory=tmp), 0)
            upload.assert_not_called()

    def test_upload_with_partial_translation_fails_before_any_download(self):
        with tempfile.TemporaryDirectory() as tmp, patch('main.download_video') as video, patch('main.upload_video') as upload:
            self.assertEqual(main.run_pipeline(directory=tmp, upload=True), 1)
            video.assert_not_called()
            upload.assert_not_called()
            self.assertIn('max_batches=None', (Path(tmp) / 'pipeline.log').read_text())

    def test_fourth_phase_only_runs_after_successful_full_translation(self):
        with tempfile.TemporaryDirectory() as tmp, patch('main.download_video', return_value='video.mp4'), patch('main.download_subtitle', return_value='tr.srt'), patch('main.translate_episode_subtitle', return_value='hu.srt') as translate, patch('main.upload_video', return_value='https://videa.hu/player?v=abcdefghijkl1234') as upload, patch('main.attach_subtitle') as attach:
            self.assertEqual(main.run_pipeline(directory=tmp, max_batches=None, upload=True), 0)
            self.assertIsNone(translate.call_args.kwargs['max_batches'])
            upload.assert_called_once_with('video.mp4', title='Daha 17 25 rész magyar felirattal',
                description='Daha 17 25 rész magyar felirattal. Török sorozat magyar feliratos epizódja.\n\nMagyar felirat: AI segítségével fordítva.',
                tags=['Daha 17 25 rész magyar felirattal', 'Daha 17 25 rész', 'Daha 17 25'],
                headless=True, email=None, password=None, **main.videa_session_options())
            attach.assert_called_once_with('video.mp4', 'hu.srt', **main.videa_session_options())
            self.assertEqual(json.loads((Path(tmp) / 'latest_upload.json').read_text()),
                {'episode': 25, 'url': 'https://videa.hu/player?v=abcdefghijkl1234'})
            self.assertIn('4. Videa-feltöltés', (Path(tmp) / 'pipeline.log').read_text())

    def test_translation_failure_never_uploads(self):
        with tempfile.TemporaryDirectory() as tmp, patch('main.download_video', return_value='video.mp4'), patch('main.download_subtitle', return_value='tr.srt'), patch('main.translate_episode_subtitle', side_effect=RuntimeError('failed')), patch('main.upload_video') as upload:
            self.assertEqual(main.run_pipeline(directory=tmp, max_batches=None, upload=True), 1)
            upload.assert_not_called()

    def test_upload_error_is_logged_as_fourth_phase_failure(self):
        with tempfile.TemporaryDirectory() as tmp, patch('main.download_video', return_value='video.mp4'), patch('main.download_subtitle', return_value='tr.srt'), patch('main.translate_episode_subtitle', return_value='hu.srt'), patch('main.upload_video', side_effect=RuntimeError('Videa: HTTP 500')):
            self.assertEqual(main.run_pipeline(directory=tmp, max_batches=None, upload=True), 1)
            log = (Path(tmp) / 'pipeline.log').read_text()
            self.assertIn('LEÁLLT | 4. Videa-feltöltés', log)
            self.assertIn('HTTP 500', log)

    def test_subtitle_failure_is_a_fourth_phase_failure_not_success(self):
        with tempfile.TemporaryDirectory() as tmp, patch('main.download_video', return_value='video.mp4'), patch('main.download_subtitle', return_value='tr.srt'), patch('main.translate_episode_subtitle', return_value='hu.srt'), patch('main.upload_video', return_value='https://videa.hu/player?v=abcdefghijkl1234'), patch('main.attach_subtitle', side_effect=RuntimeError('Felirat nem menthető')):
            latest = Path(tmp) / 'latest_upload.json'
            latest.write_text('{"episode": 24, "url": "previous"}')
            self.assertEqual(main.run_pipeline(directory=tmp, max_batches=None, upload=True), 1)
            self.assertEqual(json.loads(latest.read_text()), {'episode': 24, 'url': 'previous'})
            log = (Path(tmp) / 'pipeline.log').read_text()
            self.assertIn('LEÁLLT | 4. Videa-feltöltés', log)
            self.assertIn('Felirat nem menthető', log)

    def test_explicit_session_overrides_legacy_session(self):
        with patch.dict('os.environ', {'VIDEA_SESSION_PATH': '/tmp/explicit-session.json'}):
            self.assertEqual(main.videa_session_options(), {'session_path': Path('/tmp/explicit-session.json')})

    def test_existing_project_session_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'XDG_CONFIG_HOME': str(Path(tmp) / 'config')}), patch('main.__file__', str(Path(tmp) / 'main.py')):
            legacy = Path(tmp) / '.videa-session.json'
            legacy.write_text('{}')
            self.assertEqual(main.videa_session_options(), {'session_path': legacy})

    def test_without_legacy_session_package_uses_its_default(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'XDG_CONFIG_HOME': tmp}), patch('main.__file__', str(Path(tmp) / 'main.py')):
            self.assertEqual(main.videa_session_options(), {'session_path': Path(tmp) / 'videa-uploader/session.json'})

    def test_newest_session_wins_and_default_wins_ties(self):
        for legacy_time, default_time, expected in ((100, 200, 'default'), (200, 100, 'legacy'), (100, 100, 'default')):
            with self.subTest(legacy=legacy_time, default=default_time), tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'XDG_CONFIG_HOME': str(Path(tmp) / 'config')}), patch('main.__file__', str(Path(tmp) / 'main.py')):
                legacy = Path(tmp) / '.videa-session.json'
                default = Path(tmp) / 'config/videa-uploader/session.json'
                default.parent.mkdir(parents=True)
                legacy.write_text('{}')
                default.write_text('{}')
                os.utime(legacy, (legacy_time, legacy_time))
                os.utime(default, (default_time, default_time))
                self.assertEqual(main.videa_session_options(), {'session_path': default if expected == 'default' else legacy})

    def test_fresh_cli_session_is_passed_to_both_upload_and_subtitle(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'XDG_CONFIG_HOME': str(Path(tmp) / 'config')}), patch('main.__file__', str(Path(tmp) / 'main.py')):
            legacy = Path(tmp) / '.videa-session.json'
            default = Path(tmp) / 'config/videa-uploader/session.json'
            default.parent.mkdir(parents=True)
            legacy.write_text('{}')
            default.write_text('{}')
            os.utime(legacy, (100, 100))
            os.utime(default, (200, 200))
            with patch('main.download_video', return_value='video.mp4'), patch('main.download_subtitle', return_value='tr.srt'), patch('main.translate_episode_subtitle', return_value='hu.srt'), patch('main.upload_video', return_value='https://videa.hu/player?v=abcdefghijkl1234') as upload, patch('main.attach_subtitle') as attach:
                self.assertEqual(main.run_pipeline(directory=tmp, max_batches=None, upload=True), 0)
                self.assertEqual(upload.call_args.kwargs['session_path'], default)
                self.assertEqual(attach.call_args.kwargs['session_path'], default)
            log = (Path(tmp) / 'pipeline.log').read_text()
            self.assertIn(f'Belépési munkamenet: {default}', log)

    def test_environment_credentials_are_explicitly_passed_only_to_upload(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {
            'VIDEA_EMAIL': 'test@example.com', 'VIDEA_PASSWORD': 'test-only-password',
            'VIDEA_SESSION_PATH': '/tmp/explicit-session.json',
        }), patch('main.download_video', return_value='video.mp4'), patch('main.download_subtitle', return_value='tr.srt'), patch('main.translate_episode_subtitle', return_value='hu.srt'), patch('main.upload_video', return_value='https://videa.hu/player?v=abcdefghijkl1234') as upload, patch('main.attach_subtitle') as attach:
            self.assertEqual(main.run_pipeline(episode=26, directory=tmp, max_batches=None, upload=True), 0)
            upload.assert_called_once_with('video.mp4', title='Daha 17 26 rész magyar felirattal',
                description='Daha 17 26 rész magyar felirattal. Török sorozat magyar feliratos epizódja.\n\nMagyar felirat: AI segítségével fordítva.',
                tags=['Daha 17 26 rész magyar felirattal', 'Daha 17 26 rész', 'Daha 17 26'],
                headless=True, email='test@example.com', password='test-only-password',
                session_path=Path('/tmp/explicit-session.json'))
            self.assertNotIn('force', upload.call_args.kwargs)
            attach.assert_called_once_with('video.mp4', 'hu.srt', session_path=Path('/tmp/explicit-session.json'))

    def test_external_package_reuses_existing_video_and_subtitle_receipts_offline(self):
        self.assertIs(main.upload_video, videa_uploader.upload_video)
        self.assertIs(main.attach_subtitle, videa_uploader.attach_subtitle)
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'Daha17_25_1080p.mp4'
            subtitle = Path(tmp) / 'Daha17_25_1080p.hu.srt'
            video.write_bytes(b'video')
            subtitle.write_text(SRT)
            stat = video.stat()
            state = {'file': {'path': str(video), 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns},
                     'status': 'complete', 'vcode': 'abcdefghijkl1234',
                     'url': 'https://videa.hu/player?v=abcdefghijkl1234',
                     'subtitles': {'Magyar': {'hash': digest({'name': 'Magyar', 'srt': SRT}),
                         'status': 'complete', 'st_id': 123}}}
            receipt = video.with_suffix('.videa.json')
            receipt.write_text(json.dumps(state))
            original_receipt = receipt.read_bytes()
            with patch('main.download_video', return_value=video), patch('main.download_subtitle', return_value=Path(tmp) / 'tr.srt'), patch('main.translate_episode_subtitle', return_value=subtitle), patch('videa_uploader.upload.sync_playwright', side_effect=AssertionError('Nem szabad új videót feltölteni.')) as browser, patch('videa_uploader.subtitles.sync_playwright', side_effect=AssertionError('Nem szabad új feliratot csatolni.')) as api:
                self.assertEqual(main.run_pipeline(directory=tmp, max_batches=None, upload=True), 0)
                browser.assert_not_called()
                api.assert_not_called()
            self.assertEqual(receipt.read_bytes(), original_receipt)
