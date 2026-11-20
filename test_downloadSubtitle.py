import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import downloadSubtitle


class DownloadSubtitleTests(unittest.TestCase):
    def test_subtitle_relative_and_absolute_urls(self):
        page_url = 'https://engelsiz.kanald.com.tr/daha-17/bolumler/daha-17-24-bolum'
        content = b'1\n00:00:01,000 --> 00:00:02,000\nMerhaba\n'
        for link, expected in (
            ('/sub/doy24.srt', 'https://engelsiz.kanald.com.tr/sub/doy24.srt'),
            ('https://cdn.example.com/doy24.srt?a=1&amp;b=2', 'https://cdn.example.com/doy24.srt?a=1&b=2'),
        ):
            with self.subTest(link=link), tempfile.TemporaryDirectory() as tmp, patch('downloadSubtitle.requests.get') as get:
                page = MagicMock(url=page_url, text=f'<a href="/doy23.srt">old</a><a href="{link}">subtitle</a>')
                get.side_effect = [page, MagicMock(content=content)]
                output = downloadSubtitle.download_subtitle(24, tmp)
                self.assertEqual(output.name, 'Daha17_24_1080p.tr.srt')
                self.assertEqual(output.read_bytes(), content)
                self.assertEqual(get.call_args.args[0], expected)

    def test_missing_subtitle_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloadSubtitle.requests.get') as get:
            get.return_value.text = '<a href="/doy23.srt">other episode</a>'
            self.assertIsNone(downloadSubtitle.download_subtitle(24, tmp))
            self.assertEqual(get.call_count, 1)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_invalid_subtitle_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloadSubtitle.requests.get') as get:
            get.side_effect = [MagicMock(url='https://example.com/page', text='"/doy24.srt"'), MagicMock(content=b'<html>Error</html>')]
            with patch('sys.stderr') as stderr:
                self.assertIsNone(downloadSubtitle.download_subtitle(24, tmp))
                self.assertIn('SRT', ''.join(call.args[0] for call in stderr.write.call_args_list))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_existing_subtitle_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloadSubtitle.requests.get') as get:
            output = Path(tmp) / 'Daha17_24_1080p.tr.srt'
            output.write_bytes(b'existing')
            self.assertEqual(downloadSubtitle.download_subtitle(24, tmp), output)
            self.assertEqual(output.read_bytes(), b'existing')
            get.assert_not_called()


    def test_network_error_is_handled_in_subtitle_module(self):
        with patch('downloadSubtitle._download_subtitle', side_effect=downloadSubtitle.requests.RequestException('network')), patch('sys.stderr') as stderr:
            self.assertIsNone(downloadSubtitle.download_subtitle(25, '.'))
            self.assertIn('sikertelen', ''.join(call.args[0] for call in stderr.write.call_args_list))

    def test_interrupt_exits_with_130(self):
        with patch('downloadSubtitle._download_subtitle', side_effect=KeyboardInterrupt), patch('sys.stderr'):
            with self.assertRaises(SystemExit) as error:
                downloadSubtitle.download_subtitle(25, '.')
            self.assertEqual(error.exception.code, 130)


if __name__ == '__main__':
    unittest.main()
