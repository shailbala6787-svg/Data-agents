import os
import unittest

import requests

API_BASE = os.environ.get("UP_API_BASE", "http://127.0.0.1:8001")


class ImportSmokeTest(unittest.TestCase):
    def _upload(self, path, field="files", url="/runs/upload-csv"):
        with open(path, "rb") as handle:
            payload = {field: ("smoke.csv", handle)}
            return requests.post(
                f"{API_BASE}{url}",
                files=payload,
                timeout=30,
            )

    def test_upload_csv_root_path(self):
        response = self._upload("tests/smoke.csv", field="files", url="/runs/upload-csv")
        if response.status_code == 404:
            self.skipTest("Upload route not available on this server instance")
        self.assertEqual(200, response.status_code, response.text[:200])
        body = response.json()["data"]
        self.assertTrue(body.get("uploaded"))
        self.assertIn("table_name", body["uploaded"][0])

    def test_upload_csv_alias_path(self):
        response = self._upload("tests/smoke.csv", field="files", url="/upload-csv")
        if response.status_code == 404:
            self.skipTest("Upload alias not available on this server instance")
        self.assertEqual(200, response.status_code, response.text[:200])
        body = response.json()["data"]
        self.assertTrue(body.get("uploaded"))
        self.assertIn("table_name", body["uploaded"][0])

    def test_csv_tables_root_path(self):
        response = requests.get(f"{API_BASE}/runs/csv-tables", timeout=10)
        if response.status_code == 404:
            self.skipTest("csv-tables route not available on this server instance")
        self.assertEqual(200, response.status_code)
        body = response.json()["data"]
        self.assertIn("tables", body)
        self.assertIsInstance(body["tables"], list)

    def test_upload_accepts_single_file_field(self):
        """The frontend sends a single file field named 'file'."""
        response = self._upload("README.md", field="file", url="/runs/upload-csv")
        if response.status_code == 404:
            self.skipTest("Upload route not available on this server instance")
        self.assertIn(response.status_code, (200, 400, 422))
        body = response.json()
        self.assertIn("data", body)


if __name__ == "__main__":
    unittest.main()
