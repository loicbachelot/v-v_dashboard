# Upload Lambda regression tests

Run with the project's configured Python interpreter:

```text
python -m unittest discover -s tests -v
```

The environment needs the Lambda runtime dependencies, including `boto3`,
`pandas`, `numpy`, `scipy`, `scikit-learn`, and a Parquet engine (`pyarrow`).
Missing dependencies fail the suite; the TTPV1 checks are not skipped.

`test_ttpv1_uploads.py` loads the repository's actual `ttpv1.json`, checks that
legacy template expansion leaves it unchanged, and processes a synthetic ZIP
containing one file from each of its six categories. Parsing, KDTree
interpolation, Parquet writing, and Parquet reading use the real libraries.
Only AWS access is mocked; generated upload bytes and metadata are captured
before temporary files are removed.

For these numerical regression tests, a copy of the template reduces the two
surface grids from 1001×1001 to 3×3 while keeping their original axes and bounds.
The repository template is not edited. This verifies processing behavior,
not full-size grid performance or a deployed AWS integration.

`test_lambda_process_uploads.py` also checks compact TSHA source/variant/gage
expansion, prefix matching, and malformed columns. Its lightweight flow tests
use placeholder Parquet output; TTPV1 exercises real serialization separately.
