import json
import os
import tempfile
import unittest
from pathlib import Path

from backend.services.db.connector import DatabaseConfigurationError, validate_sqlite_relative_path
from backend.services.db.generate_demo_db import create_demo_database
from backend.services.db.scanner import scan_database


class DatabaseScannerTests(unittest.TestCase):
    def test_sqlite_hybrid_scan_finds_expected_pii_without_returning_raw_values(self):
        original_root = os.environ.get("DB_SQLITE_ROOT")

        with tempfile.TemporaryDirectory() as temp_directory:
            try:
                os.environ["DB_SQLITE_ROOT"] = temp_directory
                database_path = Path(temp_directory) / "demo.db"
                create_demo_database(database_path)

                result = scan_database({"engine": "sqlite", "sqlite_path": "demo.db"})
                findings = result["findings"]

                self.assertTrue(
                    any(
                        item["table"] == "users"
                        and item["column"] == "email"
                        and item["pii_type"] == "Email"
                        and item["method"] == "metadata+regex"
                        for item in findings
                    )
                )
                self.assertTrue(
                    any(
                        item["table"] == "contacts"
                        and item["column"] == "primary_contact"
                        and item["pii_type"] == "Phone"
                        and item["method"] == "regex"
                        for item in findings
                    )
                )
                self.assertTrue(
                    any(
                        item["table"] == "customer_data"
                        and item["column"] == "identifier"
                        and item["pii_type"] == "PAN"
                        for item in findings
                    )
                )

                # The scanner may use raw values briefly in memory, but must never return them.
                serialised_result = json.dumps(result)
                self.assertNotIn("ananya.rao@example.test", serialised_result)
                self.assertNotIn("9876543210", serialised_result)
            finally:
                if original_root is None:
                    os.environ.pop("DB_SQLITE_ROOT", None)
                else:
                    os.environ["DB_SQLITE_ROOT"] = original_root

    def test_sqlite_source_path_cannot_escape_approved_root(self):
        self.assertEqual(validate_sqlite_relative_path("safe_demo.db"), "safe_demo.db")

        for unsafe_path in ("../secret.db", "C:/private/secret.db", "/private/secret.db"):
            with self.subTest(unsafe_path=unsafe_path):
                with self.assertRaises(DatabaseConfigurationError):
                    validate_sqlite_relative_path(unsafe_path)


if __name__ == "__main__":
    unittest.main()