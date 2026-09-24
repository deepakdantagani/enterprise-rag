import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.profile_all import profile_files, profile_source


class ProfileTest(unittest.TestCase):
    def test_counts_sizes_empties_duplicates_and_escapes(self):
        files = [
            ("dsid_a__one.txt", b"x" * 40),
            ("dsid_a__two.txt", b""),
            ("dsid_b__three.txt", b"line one\\nline two"),
        ]
        profile = profile_files(files)
        self.assertEqual(profile["files"], 3)
        self.assertEqual(profile["empty_files"], 1)
        self.assertEqual(profile["duplicate_dsids"], 1)
        self.assertEqual(profile["json_escaped_files"], 1)
        self.assertEqual(profile["tokens"]["max"], 10)

    def test_profile_source_writes_json_from_zips(self):
        with tempfile.TemporaryDirectory() as tmp:
            archives = Path(tmp) / "demo" / "archives"
            archives.mkdir(parents=True)
            with zipfile.ZipFile(archives / "demo_slice_0001.zip", "w") as z:
                z.writestr("demo/dsid_a__x.txt", "hello\nworld")
            self.assertEqual(profile_source("demo", Path(tmp))["files"], 1)
            self.assertTrue((Path(tmp) / "demo" / "profile.json").exists())


if __name__ == "__main__":
    unittest.main()
