import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.paths import data_root,resource_root,catalog_root


class ReleasePathsTests(unittest.TestCase):
    def test_explicit_profile_does_not_require_assets_in_user_folder(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'ALBIONCRAFT_DATA_DIR':str(Path(folder)/'profile')}):
            profile=data_root()
            self.assertTrue(profile.is_dir())
            self.assertEqual(catalog_root(profile),resource_root())
            self.assertFalse((profile/'research').exists())

    def test_frozen_release_uses_local_appdata_not_executable_folder(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'LOCALAPPDATA':folder},clear=True),patch('sys.frozen',True,create=True):
            self.assertEqual(data_root(),Path(folder)/'AlbionCraft')

    def test_fixture_catalog_can_override_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture=Path(folder);(fixture/'research').mkdir();(fixture/'research/items.json').write_text('{}')
            self.assertEqual(catalog_root(fixture),fixture)

    def test_source_install_retains_existing_location(self):
        with patch.dict(os.environ,{},clear=True),patch('sys.frozen',False,create=True):
            self.assertEqual(data_root(),resource_root())
