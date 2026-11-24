import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import downloader


class DownloaderTests(unittest.TestCase):
    def test_missing_directory_fails_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('downloader.requests.get') as get:
                with self.assertRaisesRegex(ValueError, 'nem létezik'):
                    downloader.run(Path(tmp) / 'missing')
                get.assert_not_called()

    def test_file_cannot_be_directory(self):
        with tempfile.NamedTemporaryFile() as file:
            with self.assertRaisesRegex(ValueError, 'nem mappa'):
                downloader.validate_download_directory(file.name)

    def test_actual_episode_used_for_filename_and_safe_arguments(self):
        url = 'https://vod3.cf.dmcdn.net/sec2(token)/video/fmp4/1/h264_aac_fhd/2/manifest.m3u8'
        with tempfile.TemporaryDirectory(prefix='daha 17 ') as tmp:
            def download(command, **kwargs):
                self.assertTrue(kwargs['check'])
                if command[0] == '/usr/bin/ffmpeg':
                    self.assertIn('-xerror', command)
                    self.assertEqual(command[command.index('-i') + 1], str(Path(tmp) / 'Daha17_26_1080p.mp4'))
                    return
                self.assertEqual(command[-2:], ['--', url])
                self.assertEqual(command[command.index('-P') + 1], tmp)
                self.assertEqual(command[command.index('-o') + 1], 'Daha17_26_1080p.%(ext)s')
                self.assertIn('--abort-on-unavailable-fragments', command)
                self.assertEqual(command[command.index('-N') + 1], '4')
                (Path(tmp) / 'Daha17_26_1080p.mp4').write_bytes(b'video')

            with patch('downloader.requests.get') as get, patch('downloader.find_manifest', return_value=url), patch('downloader.shutil.which', side_effect=lambda name: '/usr/bin/' + name), patch('downloader.subprocess.run', side_effect=download):
                get.return_value.text = '<h1>Daha 17 26. Bölüm</h1>'
                self.assertEqual(downloader.run(tmp), Path(tmp) / 'Daha17_26_1080p.mp4')

    def test_failed_download_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloader.shutil.which', return_value='/usr/bin/tool'), patch('downloader.subprocess.run', side_effect=subprocess.CalledProcessError(1, ['yt-dlp'])):
            with self.assertRaisesRegex(RuntimeError, 'sikertelen'):
                downloader.download_episode('https://example.com/video.m3u8', 25, tmp)

    def test_existing_mp4_is_checked_without_network_or_downloader(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloader.requests.get') as get, patch('downloader.shutil.which', return_value='/usr/bin/ffmpeg'), patch('downloader.subprocess.run') as execute:
            output = Path(tmp) / 'Daha17_25_1080p.mp4'
            output.write_bytes(b'video')
            self.assertEqual(downloader.run(tmp), output)
            get.assert_not_called()
            execute.assert_called_once()
            self.assertEqual(execute.call_args.args[0][0], '/usr/bin/ffmpeg')

    def test_existing_empty_mp4_stops_without_network(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloader.requests.get') as get:
            (Path(tmp) / 'Daha17_25_1080p.mp4').touch()
            with self.assertRaisesRegex(RuntimeError, 'üres'):
                downloader.run(tmp)
            get.assert_not_called()

    def test_exact_episode_rejects_newer_video_before_download(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloader.requests.get') as get, patch('downloader.find_manifest') as manifest:
            get.return_value.text = '<h1>Daha 17 26. Bölüm</h1>'
            with self.assertRaisesRegex(RuntimeError, '25.*26'):
                downloader.run(tmp, target_episode=25, page_url=downloader.URL, exact_episode=True)
            manifest.assert_not_called()

    def test_exact_episode_uses_archived_page_when_latest_episode_is_newer(self):
        archive = 'https://www.kanald.com.tr/daha-17/bolumler/daha-17-25-bolum'
        listing = ('<a href="/daha-17/bolumler/daha-17-son-bolum">Daha 17 26. Bölüm</a>'
                   '<a href="/daha-17/bolumler/daha-17-25-bolum">Daha 17 25. Bölüm</a>')
        with tempfile.TemporaryDirectory() as tmp, patch('downloader.requests.get') as get, patch('downloader.find_manifest', return_value='https://example.com/video.m3u8') as manifest, patch('downloader.download_episode', return_value=Path(tmp) / 'video.mp4') as download:
            pages = {downloader.EPISODES_URL: listing, archive: '<h1>Daha 17 25. Bölüm</h1>',
                     downloader.URL: '<h1>Daha 17 26. Bölüm</h1>'}
            get.side_effect = lambda url, **kwargs: MagicMock(text=pages[url])
            self.assertEqual(downloader.run(tmp, target_episode=25, exact_episode=True), download.return_value)
            self.assertEqual([call.args[0] for call in get.call_args_list], [downloader.EPISODES_URL, archive])
            self.assertEqual(manifest.call_args.args[1], archive)
            download.assert_called_once_with('https://example.com/video.m3u8', 25, Path(tmp))

    def test_exact_latest_episode_uses_its_actual_link(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloader.requests.get') as get, patch('downloader.find_manifest', return_value='manifest'), patch('downloader.download_episode') as download:
            get.side_effect = [MagicMock(text='<a href="/daha-17/bolumler/daha-17-son-bolum"><img alt="Daha 17 26. Bölüm"></a>'), MagicMock(text='<h1>Daha 17 26. Bölüm</h1>')]
            downloader.run(tmp, target_episode=26, exact_episode=True)
            self.assertEqual(get.call_args.args[0], downloader.URL)
            self.assertEqual(download.call_args.args[1], 26)

    def test_missing_episode_in_listing_stops_before_manifest_lookup(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloader.requests.get') as get, patch('downloader.find_manifest') as manifest:
            get.return_value.text = '<a href="/daha-17/bolumler/daha-17-son-bolum">Daha 17 26. Bölüm</a>'
            self.assertIsNone(downloader.run(tmp, target_episode=27, exact_episode=True))
            get.assert_called_once_with(downloader.EPISODES_URL, timeout=20)
            manifest.assert_not_called()

    def test_older_episode_does_not_start_player_or_download(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloader.requests.get') as get, patch('downloader.find_manifest') as find:
            get.return_value.text = '<h1>Daha 17 24. Bölüm</h1>'
            self.assertIsNone(downloader.run(tmp))
            find.assert_not_called()

    def test_invalid_media_responses(self):
        soup = downloader.BeautifulSoup('<div class="player-container" data-pq-type="Dailymotion" data-id="123"></div>', 'html.parser')
        responses = [None, [], {'data': None}, {'data': {'media': None}},
                     {'data': {'media': {'link': None}}},
                     {'data': {'media': {'link': {'securePath': None, 'serviceName': 'player'}}}}]
        for payload in responses:
            with self.subTest(payload=payload), patch('downloader.requests.get') as get, patch('downloader.sync_playwright') as browser:
                get.return_value.json.return_value = payload
                with self.assertRaises(RuntimeError):
                    downloader.find_manifest(soup)
                browser.assert_not_called()
        with patch('downloader.requests.get') as get:
            get.return_value.json.side_effect = ValueError('invalid JSON')
            with self.assertRaisesRegex(RuntimeError, 'médiaválasz'):
                downloader.find_manifest(soup)

    def test_missing_player_fails_before_network(self):
        for html in ('', '<div class="player-container" data-pq-type="Dailymotion"></div>'):
            with self.subTest(html=html), patch('downloader.requests.get') as get:
                with self.assertRaisesRegex(RuntimeError, 'lejátszója'):
                    downloader.find_manifest(downloader.BeautifulSoup(html, 'html.parser'))
                get.assert_not_called()

    def test_manifest_selection_from_master_playlist(self):
        url = 'https://vod3.cf.dmcdn.net/video/h264_aac_fhd/2/manifest.m3u8'
        soup = downloader.BeautifulSoup('<div class="player-container" data-pq-type="Dailymotion" data-id="123"></div>', 'html.parser')
        with patch('downloader.requests.get') as get, patch('downloader.sync_playwright') as playwright:
            get.return_value.json.return_value = {'data': {'media': {'link': {'securePath': 'video123', 'serviceName': 'player123'}}}}
            browser = playwright.return_value.__enter__.return_value.chromium.launch.return_value
            context = browser.new_context.return_value
            page = context.new_page.return_value
            master = MagicMock(url='https://vod3.cf.dmcdn.net/master.m3u8', ok=True)
            master.text.return_value = '\ufeff#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100\n/video/h264_aac_fhd/2/manifest.m3u8\n'
            page.goto.side_effect = lambda *a, **kw: page.on.call_args.args[1](master)
            context.request.get.return_value.text.return_value = '#EXTM3U\n'
            self.assertEqual(downloader.find_manifest(soup), url)
            context.request.get.assert_called_once_with(url, timeout=30000)
            browser.close.assert_called_once()

    def test_missing_or_empty_download_is_rejected(self):
        for content in (None, b''):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp, patch('downloader.shutil.which', return_value='/usr/bin/tool'), patch('downloader.subprocess.run') as run:
                if content is not None:
                    run.side_effect = lambda *a, **kw: (Path(tmp) / 'Daha17_25_1080p.mp4').write_bytes(content)
                with self.assertRaises(RuntimeError):
                    downloader.download_episode('https://example.com/video.m3u8', 25, tmp)
                self.assertEqual(run.call_count, 1)

    def test_corrupt_download_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloader.shutil.which', side_effect=lambda name: '/usr/bin/' + name):
            def execute(command, **kwargs):
                if command[0] == '/usr/bin/yt-dlp':
                    (Path(tmp) / 'Daha17_25_1080p.mp4').write_bytes(b'corrupt')
                else:
                    raise subprocess.CalledProcessError(1, command)
            with patch('downloader.subprocess.run', side_effect=execute):
                with self.assertRaisesRegex(RuntimeError, 'sérült'):
                    downloader.download_episode('https://example.com/video.m3u8', 25, tmp)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg szükséges')
    def test_real_ffmpeg_accepts_video_and_rejects_corrupt_file(self):
        real_run = subprocess.run
        ffmpeg = shutil.which('ffmpeg')
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / 'fixture.mp4'
            real_run([ffmpeg, '-nostdin', '-v', 'error', '-f', 'lavfi',
                      '-i', 'color=size=16x16:rate=1', '-t', '1', '-c:v', 'mpeg4',
                      str(fixture)], check=True, capture_output=True)
            valid_video = fixture.read_bytes()
            for content in (valid_video, b'not an MP4'):
                with self.subTest(valid=content == valid_video):
                    output = Path(tmp) / 'Daha17_25_1080p.mp4'
                    def execute(command, **kwargs):
                        if command[0] == 'fake-yt-dlp':
                            output.write_bytes(content)
                            return
                        return real_run(command, **kwargs)
                    with patch('downloader.shutil.which', side_effect=lambda name: ffmpeg if name == 'ffmpeg' else 'fake-yt-dlp'), patch('downloader.subprocess.run', side_effect=execute):
                        if content == valid_video:
                            self.assertEqual(downloader.download_episode('https://example.com/video.m3u8', 25, tmp), output)
                        else:
                            with self.assertRaisesRegex(RuntimeError, 'sérült'):
                                downloader.download_episode('https://example.com/video.m3u8', 25, tmp)
                    output.unlink()


if __name__ == '__main__':
    unittest.main()
