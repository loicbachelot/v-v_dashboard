"""TTPV1 upload regressions with real interpolation and Parquet artifacts."""

import copy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import numpy as np
import pandas as pd

from test_lambda_process_uploads import FakeS3, PROJECT_ROOT, load_lambda_module, make_zip


TEMPLATE_PATH = PROJECT_ROOT / "resources" / "benchmark_templates" / "ttpv1.json"


class TTPV1UploadTests(TestCase):
    def setUp(self):
        # Only AWS clients are mocked during import. Missing sklearn or PyArrow
        # dependencies must fail the suite instead of bypassing surface tests.
        self.lambda_module = load_lambda_module()
        self.original_template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
        self.template = copy.deepcopy(self.original_template)
        self.files = {}
        self.expected_frames = {}
        self.names_by_prefix = {}

        for entry in self.template["files"]:
            columns = [var["name"] for var in entry["var_list"]]
            filename = f"nested/results/{entry['list_of_receivers'][0]}.csv"
            if entry["graph_type"] == "surface":
                axes = list(entry["grid"])
                for axis in axes:
                    entry["grid"][axis]["n"] = 3
                a0, a1 = axes
                lo0, hi0 = entry["grid"][a0]["min"], entry["grid"][a0]["max"]
                lo1, hi1 = entry["grid"][a1]["min"], entry["grid"][a1]["max"]
                frame = pd.DataFrame({
                    a0: [lo0, hi0, lo0, hi0],
                    a1: [lo1, lo1, hi1, hi1],
                    **{col: [float(i + 1)] * 4
                       for i, col in enumerate(columns) if col not in axes},
                }, columns=columns)
            else:
                frame = pd.DataFrame({
                    col: [float(i), float(i + 1)] for i, col in enumerate(columns)
                }, columns=columns)

            header = (
                f"# File: {Path(filename).name}\n"
                "# simulation = TTPV1 fixture\n"
                f"# category: {entry['name']}\n"
            )
            self.files[filename] = header + frame.to_csv(sep=" ", index=False)
            self.expected_frames[entry["prefix"]] = frame
            self.names_by_prefix[entry["prefix"]] = filename

        # Neither file should be picked up by TTPV1's CSV prefix matching.
        self.files["nested/results/surfdef.txt"] = "invalid data"
        self.files["nested/results/unrelated.csv"] = "invalid data"

    def run_process(self, files):
        fake_s3 = FakeS3(self.template, make_zip(files))
        self.lambda_module.s3 = fake_s3
        with TemporaryDirectory() as output_folder:
            summary = self.lambda_module.process_zip(
                "incoming-bucket", "upload/ttpv1/submitter_v1.zip", "ttpv1",
                "submitter", "v1", user_metadata={"userid": "user-1"},
                output_folder=output_folder,
            )
        return fake_s3, summary

    @staticmethod
    def output_key(filename):
        return f"public_ds/ttpv1/submitter_v1/{Path(filename).stem}.parquet"

    def metadata(self, fake_s3):
        return json.loads(fake_s3.objects["public_ds/ttpv1/submitter_v1/metadata.json"])

    def test_expansion_preserves_actual_ttpv1_template_unchanged(self):
        before = copy.deepcopy(self.original_template)
        expanded = self.lambda_module.expand_template_files(self.original_template)
        self.assertIs(expanded, self.original_template["files"])
        self.assertEqual(self.original_template, before)
        self.assertEqual(len(expanded), 6)
        self.assertEqual(sum(entry["graph_type"] == "surface" for entry in expanded), 2)
        for entry in expanded:
            if "grid" in entry:
                self.assertEqual(entry["grid"]["x"]["n"], 1001)
                self.assertEqual(entry["grid"]["y"]["n"], 1001)

    def test_all_six_categories_write_readable_parquet_and_metadata(self):
        fake_s3, summary = self.run_process(self.files)
        self.assertCountEqual(summary["successfulFiles"], self.names_by_prefix.values())
        self.assertEqual(summary["missingFiles"], [])
        self.assertEqual(summary["filesWithErrors"], [])
        self.assertEqual(len(fake_s3.uploads), 7)
        self.assertIn(("incoming-bucket", "benchmark_templates/ttpv1.json"), fake_s3.get_requests)

        metadata = self.metadata(fake_s3)
        self.assertCountEqual(metadata["processed_files"], self.names_by_prefix.values())
        self.assertEqual(set(metadata), {*self.names_by_prefix, "processed_files"})
        for entry in self.template["files"]:
            with self.subTest(category=entry["name"]):
                prefix = entry["prefix"]
                filename = self.names_by_prefix[prefix]
                result = pd.read_parquet(io.BytesIO(fake_s3.objects[self.output_key(filename)]))
                self.assertEqual(list(result.columns), [var["name"] for var in entry["var_list"]])
                if entry["graph_type"] == "surface":
                    self.assertEqual(len(result), 9)
                    self.assertEqual(len(result[["x", "y"]].drop_duplicates()), 9)
                    for axis, spec in entry["grid"].items():
                        np.testing.assert_allclose(
                            sorted(result[axis].unique()), np.linspace(spec["min"], spec["max"], 3)
                        )
                    for col in result.columns:
                        if col not in entry["grid"]:
                            np.testing.assert_allclose(result[col], self.expected_frames[prefix][col].iloc[0])
                else:
                    pd.testing.assert_frame_equal(result, self.expected_frames[prefix])

                self.assertEqual(metadata[prefix], {
                    Path(filename).stem: {"simulation": "TTPV1 fixture", "category": entry["name"]}
                })

        for _filename, bucket, _key, extra_args in fake_s3.uploads:
            self.assertEqual(bucket, "benchmark-vv-data")
            self.assertEqual(extra_args, {"Metadata": {"userid": "user-1"}})

    def test_missing_category_is_reported_while_other_categories_upload(self):
        files = dict(self.files)
        missing_filename = self.names_by_prefix["tsunami"]
        del files[missing_filename]
        fake_s3, summary = self.run_process(files)
        self.assertEqual(summary["missingFiles"], [{
            "prefix": "tsunami", "fileType": "csv", "expectedPattern": "tsunami*.csv"
        }])
        self.assertEqual(summary["filesWithErrors"], [])
        self.assertCountEqual(summary["successfulFiles"],
                              [name for name in self.names_by_prefix.values() if name != missing_filename])
        self.assertNotIn(self.output_key(missing_filename), fake_s3.objects)
        self.assertNotIn("tsunami", self.metadata(fake_s3))
        self.assertCountEqual(self.metadata(fake_s3)["processed_files"], summary["successfulFiles"])

    def test_malformed_fault_columns_do_not_block_other_categories(self):
        files = dict(self.files)
        filename = self.names_by_prefix["fault"]
        files[filename] = files[filename].replace("t h-slip ", "t unexpected ")
        with self.assertWarnsRegex(UserWarning, "does not match the expected structure"):
            fake_s3, summary = self.run_process(files)
        self.assertEqual(summary["missingFiles"], [])
        self.assertEqual(len(summary["filesWithErrors"]), 1)
        error = summary["filesWithErrors"][0]
        self.assertEqual(error["fileName"], filename)
        self.assertIn("Expected columns", error["error"])
        self.assertIn("unexpected", error["error"])
        self.assertNotIn(self.output_key(filename), fake_s3.objects)
        self.assertCountEqual(summary["successfulFiles"],
                              [name for name in self.names_by_prefix.values() if name != filename])
        self.assertCountEqual(self.metadata(fake_s3)["processed_files"], summary["successfulFiles"])
