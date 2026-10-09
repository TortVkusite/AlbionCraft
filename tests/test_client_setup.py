import gzip,hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
from app.client_setup import install_client,download_package

class SetupTests(unittest.TestCase):
    def test_unpack_client_and_repeat_without_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=root/'client.gz';archive.write_bytes(gzip.compress(b'MZtest-program'))
            installed=install_client(archive,root/'tools')
            self.assertEqual(installed.read_bytes(),b'MZtest-program');stamp=installed.stat().st_mtime_ns
            self.assertEqual(install_client(archive,root/'tools').stat().st_mtime_ns,stamp)
            archive.write_bytes(gzip.compress(b'not an exe'))
            with self.assertRaises(ValueError):install_client(archive,root/'tools')
            self.assertEqual(installed.read_bytes(),b'MZtest-program')
    def test_download_verifies_cache_and_rejects_corruption(self):
        class Response(BytesIO):headers={}
        data=b'MZgood';manifest={'test':('test.exe','https://example.invalid/file',hashlib.sha256(data).hexdigest())}
        with tempfile.TemporaryDirectory() as folder,patch('app.client_setup.PACKAGES',manifest):
            with patch('app.client_setup.urlopen',return_value=Response(data)):
                path=download_package('test',folder);self.assertEqual(path.read_bytes(),data)
            with patch('app.client_setup.urlopen',side_effect=AssertionError('Valid cache must not download')):self.assertEqual(download_package('test',folder),path)
            path.write_bytes(b'bad')
            with patch('app.client_setup.urlopen',return_value=Response(b'bad download')):
                with self.assertRaises(ValueError):download_package('test',folder)
            self.assertFalse(path.with_suffix('.exe.part').exists())

if __name__=='__main__':unittest.main()
