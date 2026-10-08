"""Offline compatibility tests for upload ZIP processing."""

import importlib.util
import io
import json
import os
import zipfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import boto3
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAMBDA_PATH = PROJECT_ROOT / "lambda_process_uploads" / "lambda_function.py"


class FakeBody:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data


class FakeS3:
    def __init__(self, template, zip_bytes):
        self.template = template
        self.zip_bytes = zip_bytes
        self.uploads = []
        self.objects = {}
        self.get_requests = []

    def get_object(self, Bucket, Key):
        self.get_requests.append((Bucket, Key))
        if Key.startswith("benchmark_templates/"):
            body = json.dumps(self.template).encode("utf-8")
        else:
            body = self.zip_bytes
        return {"Body": FakeBody(body)}

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        self.uploads.append((Path(filename).name, bucket, key, ExtraArgs or {}))
        self.objects[key] = Path(filename).read_bytes()


def load_lambda_module():
    """Import the Lambda without making any AWS requests."""
    module_name = "lambda_process_uploads_under_test"
    spec = importlib.util.spec_from_file_location(module_name, LAMBDA_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, {"TABLE_NAME": "upload-test-table"}), \
            patch.object(boto3, "client", return_value=object()), patch.object(
                boto3, "resource", return_value=type("Dynamo", (), {"Table": lambda self, _name: object()})()
            ):
        spec.loader.exec_module(module)
    return module


def make_zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, contents in files.items():
            archive.writestr(name, contents)
    return buffer.getvalue()


LEGACY_TEMPLATE = {
    "name": "legacy-fixture",
    "files": [
        {
            "name": "time_series",
            "prefix": "legacy_",
            "file_type": "txt",
            "graph_type": "timeseries",
            "list_of_receivers": ["legacy_gauge00001"],
            "var_list": [
                {"name": "t", "unit": "s", "description": "time"},
                {"name": "depth", "unit": "m", "description": "depth"},
            ],
        }
    ],
}

COMPACT_TSHA_TEMPLATE = {
    "name": "TSHA-BP1",
    "source_series": {
        "sources": ["BL13M", "BL14M"],
        "gages": ["00001", "00002"],
        "variants": [
            {
                "name": "nothing",
                "prefix_pattern": "{source}_gauge",
                "receiver_pattern": "{source}_gauge{gage}",
            },
            {
                "name": "instant",
                "prefix_pattern": "{source}_instant_gauge",
                "receiver_pattern": "{source}_instant_gauge{gage}",
            },
        ],
        "content": "Time-series data",
        "graph_type": "timeseries",
        "var_list": [
            {"name": "t", "unit": "s", "description": "time"},
            {"name": "depth", "unit": "m", "description": "depth"},
            {"name": "surf", "unit": "m", "description": "surface"},
        ],
        "file_type": "txt",
    },
}


class ProcessZipCompatibilityTests(TestCase):
    def setUp(self):
        self.lambda_module = load_lambda_module()

    def run_process(self, template, files, tmp_path):
        fake_s3 = FakeS3(template, make_zip(files))
        self.lambda_module.s3 = fake_s3
        def fake_to_parquet(frame, filename, index=False):
            Path(filename).write_bytes(b"test parquet placeholder")

        with patch.object(pd.DataFrame, "to_parquet", fake_to_parquet):
            summary = self.lambda_module.process_zip(
                "incoming-bucket",
                "upload.zip",
                template["name"],
                "submitter",
                "v1",
                user_metadata={"userid": "user-1"},
                output_folder=str(tmp_path),
            )
        return fake_s3, summary

    def test_legacy_template_still_processes_with_existing_output_contract(self):
        with self.subTest("legacy ZIP processing"):
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as tmp:
                fake_s3, summary = self.run_process(
                    LEGACY_TEMPLATE,
                    {"nested/legacy_gauge00001.txt": "# source = legacy\nt depth\n0 1\n1 2\n"},
                    Path(tmp),
                )

        self.assertEqual(summary["successfulFiles"], ["nested/legacy_gauge00001.txt"])
        self.assertEqual(summary["missingFiles"], [])
        self.assertEqual(summary["filesWithErrors"], [])
        self.assertIn(
            ("legacy_gauge00001.parquet", "benchmark-vv-data",
             "public_ds/legacy-fixture/submitter_v1/legacy_gauge00001.parquet",
             {"Metadata": {"userid": "user-1"}}),
            fake_s3.uploads,
        )
        metadata_upload = next(row for row in fake_s3.uploads if row[0] == "metadata.json")
        self.assertEqual(metadata_upload[2], "public_ds/legacy-fixture/submitter_v1/metadata.json")

    def test_compact_source_series_processes_both_variants_and_all_gages(self):
        files = {}
        expected_names = []
        for source in COMPACT_TSHA_TEMPLATE["source_series"]["sources"]:
            for variant in COMPACT_TSHA_TEMPLATE["source_series"]["variants"]:
                for gage in COMPACT_TSHA_TEMPLATE["source_series"]["gages"]:
                    name = variant["receiver_pattern"].format(source=source, gage=gage) + ".txt"
                    files[f"{source}/{name}"] = "# source = test\nt depth surf\n0 1 2\n1 3 4\n"
                    expected_names.append(f"{source}/{name}")

        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            fake_s3, summary = self.run_process(COMPACT_TSHA_TEMPLATE, files, Path(tmp))

        self.assertCountEqual(summary["successfulFiles"], expected_names)
        self.assertEqual(summary["missingFiles"], [])
        self.assertEqual(summary["filesWithErrors"], [])
        parquet_keys = {row[2] for row in fake_s3.uploads if row[0] != "metadata.json"}
        self.assertEqual(len(parquet_keys), len(expected_names))
        for name in expected_names:
            parquet_name = f"{Path(name).stem}.parquet"
            self.assertIn(f"public_ds/TSHA-BP1/submitter_v1/{parquet_name}", parquet_keys)

    def test_compact_variants_do_not_match_each_others_files_and_missing_prefix_is_reported(self):
        files = {
            "BL13M_gauge00001.txt": "t depth surf\n0 1 2\n",
            "BL13M_instant_gauge00001.txt": "t depth surf\n0 1 2\n",
        }
        # Restrict the fixture to one source and one gage; leave the second
        # source and gage absent so their expected prefixes are reported.
        template = json.loads(json.dumps(COMPACT_TSHA_TEMPLATE))
        template["source_series"]["sources"] = ["BL13M", "MISSING"]
        template["source_series"]["gages"] = ["00001", "00002"]

        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            fake_s3, summary = self.run_process(template, files, Path(tmp))

        processed = {Path(name).name for name in summary["successfulFiles"]}
        self.assertEqual(processed, {"BL13M_gauge00001.txt", "BL13M_instant_gauge00001.txt"})
        missing_prefixes = {entry["prefix"] for entry in summary["missingFiles"]}
        self.assertIn("MISSING_gauge", missing_prefixes)
        self.assertIn("MISSING_instant_gauge", missing_prefixes)
        uploaded_data = [row[2] for row in fake_s3.uploads if row[0] != "metadata.json"]
        self.assertEqual(len(uploaded_data), 2)

    def test_malformed_columns_are_reported_without_uploading_that_file(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            fake_s3, summary = self.run_process(
                LEGACY_TEMPLATE,
                {"legacy_gauge00001.txt": "t wrong\n0 1\n"},
                Path(tmp),
            )

        self.assertEqual(summary["successfulFiles"], [])
        self.assertEqual(len(summary["filesWithErrors"]), 1)
        self.assertIn("Expected columns", summary["filesWithErrors"][0]["error"])
        self.assertEqual([row[0] for row in fake_s3.uploads], ["metadata.json"])


class ExistingTemplatesCompatibilityTests(TestCase):
    def test_existing_benchmark_templates_keep_the_legacy_files_shape(self):
        template_dir = PROJECT_ROOT / "resources" / "benchmark_templates"
        template_paths = [p for p in template_dir.glob("*.json") if p.name != "benchmarks_list.json"]
        self.assertGreater(len(template_paths), 0)
        for path in template_paths:
            with self.subTest(template=path.name):
                template = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(template.get("files"), list)
                for entry in template["files"]:
                    self.assertTrue(entry["prefix"] is not None)
                    self.assertTrue(entry["file_type"])
                    self.assertIsInstance(entry["var_list"], list)


if __name__ == "__main__":
    import unittest

    unittest.main()
