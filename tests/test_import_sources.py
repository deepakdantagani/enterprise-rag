import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.import_sources import archives_of, import_source


class ImportSourceTest(unittest.TestCase):
    def test_archives_of_keeps_only_that_source_in_order(self):
        assets = [{"name": "a_slice_0002.zip"}, {"name": "b_slice_0001.zip"}, {"name": "a_slice_0001.zip"}]
        self.assertEqual([a["name"] for a in archives_of("a", assets)], ["a_slice_0001.zip", "a_slice_0002.zip"])

    def test_import_writes_manifest_and_raw_from_existing_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            archives = data / "demo" / "archives"
            archives.mkdir(parents=True)
            zip_path = archives / "demo_slice_0001.zip"
            with zipfile.ZipFile(zip_path, "w") as z:
                z.writestr("demo/a.txt", "hello")
                z.writestr("demo/b.txt", "world")
            digest = "sha256:" + hashlib.sha256(zip_path.read_bytes()).hexdigest()
            asset = {"name": zip_path.name, "browser_download_url": "http://unused", "digest": digest}
            manifest = import_source("demo", [asset], data_dir=data)
            self.assertEqual(manifest["archives"][0]["documents"], 2)
            self.assertEqual(json.loads((data / "demo" / "manifest.json").read_text()), manifest)
            self.assertTrue((data / "demo" / "raw" / "demo" / "a.txt").exists())

    def test_wrong_sha256_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archives = Path(tmp) / "demo" / "archives"
            archives.mkdir(parents=True)
            with zipfile.ZipFile(archives / "demo_slice_0001.zip", "w") as z:
                z.writestr("a.txt", "x")
            asset = {"name": "demo_slice_0001.zip", "browser_download_url": "http://unused", "digest": "sha256:0"}
            with self.assertRaises(ValueError):
                import_source("demo", [asset], data_dir=Path(tmp))


if __name__ == "__main__":
    unittest.main()
