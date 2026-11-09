import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class PackagedDataPathTests(unittest.TestCase):
    def test_source_path_unchanged(self):
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(app.default_data_path(), Path(app.__file__).resolve().parent / "data" / "moa.sqlite3")

    def test_frozen_data_is_not_temporary_bundle_data(self):
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "platform", "win32"), patch.dict(os.environ, {"LOCALAPPDATA": "C:/Users/Example/AppData/Local"}):
            self.assertEqual(app.default_data_path(), Path("C:/Users/Example/AppData/Local/Moa/moa.sqlite3"))

    def test_missing_environment_uses_user_profile(self):
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "platform", "win32"), patch.dict(os.environ, {"LOCALAPPDATA": ""}):
            self.assertEqual(app.default_data_path(), Path.home() / "AppData" / "Local" / "Moa" / "moa.sqlite3")


if __name__ == "__main__":
    unittest.main()
