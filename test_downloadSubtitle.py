import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import downloadSubtitle


class DownloadSubtitleTests(unittest.TestCase):
    def test_subtitle_downloads_directly_from_cdn(self):
        content = b'1\n00:00:01,000 --> 00:00:02,000\nMerhaba\n'
        with tempfile.TemporaryDirectory() as tmp, patch('downloadSubtitle.requests.get') as get:
            get.return_value.content = content
            output = downloadSubtitle.download_subtitle(24, tmp)
            self.assertEqual(output.name, 'Daha17_24_1080p.tr.srt')
            self.assertEqual(output.read_bytes(), content)
            get.assert_called_once_with(
                'https://cdn.duhnet.tv/C13/2013kanald/dizi/daha17/doy24.srt', timeout=30)

    def test_missing_subtitle_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloadSubtitle.requests.get') as get:
            get.return_value.raise_for_status.side_effect = downloadSubtitle.requests.HTTPError('404')
            with patch('sys.stderr'):
                self.assertIsNone(downloadSubtitle.download_subtitle(24, tmp))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_existing_subtitle_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloadSubtitle.requests.get') as get:
            output = Path(tmp) / 'Daha17_24_1080p.tr.srt'
            output.write_bytes(b'1\n00:00:01,000 --> 00:00:02,000\nMerhaba\n')
            self.assertEqual(downloadSubtitle.download_subtitle(24, tmp), output)
            self.assertIn(b'Merhaba', output.read_bytes())
            get.assert_not_called()


    def test_network_error_is_handled_in_subtitle_module(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloadSubtitle.requests.get', side_effect=downloadSubtitle.requests.RequestException('network')), patch('sys.stderr') as stderr:
            self.assertIsNone(downloadSubtitle.download_subtitle(25, tmp))
            self.assertIn('sikertelen', ''.join(call.args[0] for call in stderr.write.call_args_list))

    def test_invalid_http_200_response_is_not_saved_as_subtitle(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloadSubtitle.requests.get') as get:
            get.return_value.content = b'<html>Error</html>'
            with self.assertRaises(ValueError):
                downloadSubtitle.download_subtitle(25, tmp, raise_errors=True)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_failed_final_save_leaves_no_completed_subtitle(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloadSubtitle.requests.get') as get:
            get.return_value.content = b'1\n00:00:01,000 --> 00:00:02,000\nMerhaba\n'
            with patch('pathlib.Path.replace', side_effect=OSError('write failed')):
                with self.assertRaises(OSError):
                    downloadSubtitle.download_subtitle(25, tmp, raise_errors=True)
            self.assertFalse((Path(tmp) / 'Daha17_25_1080p.tr.srt').exists())
            self.assertTrue((Path(tmp) / 'Daha17_25_1080p.tr.srt.part').exists())

    def test_interrupt_exits_with_130(self):
        with tempfile.TemporaryDirectory() as tmp, patch('downloadSubtitle.requests.get', side_effect=KeyboardInterrupt), patch('sys.stderr'):
            with self.assertRaises(SystemExit) as error:
                downloadSubtitle.download_subtitle(25, tmp)
            self.assertEqual(error.exception.code, 130)


if __name__ == '__main__':
    unittest.main()
