import os
import json
import warnings
import zipfile
from datetime import datetime

import boto3
import pandas as pd
from io import StringIO, BytesIO

from sklearn.neighbors import KDTree
import numpy as np
from botocore.exceptions import NoCredentialsError, ClientError

# Initialize AWS clients
s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
table_name = os.environ["TABLE_NAME"]
table = dynamodb.Table(table_name)

def convert_seconds_to_time(seconds):
    years = seconds / (365.25 * 24 * 3600)
    days = seconds / (24 * 3600)
    hours = seconds / 3600
    return years, days, hours, seconds


def extract_header(file_header, prefix, content):
    if file_header is None:
        file_header = {}

    header_data = {}

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# File:"):
            continue
        if line.startswith("#"):
            if '=' in line:
                key, value = line[2:].strip().split('=', 1)
                header_data[key.strip()] = value.strip()
            else:
                header_data.setdefault("comments", []).append(line[2:].strip())
        else:
            break

    file_header[prefix] = header_data
    return file_header


def interpolate_data(df, grid_params, k=3, power=1.0, average_duplicates=True):
    """Regrid all numeric variables in df using k-NN inverse distance weighting (IDW).

    Parameters
    ----------
    df : DataFrame
        Must contain 'x' and 'y' columns and any number of numeric variables to interpolate.
    grid_params : dict
        {
          "x": {"min": ..., "max": ..., "n": ...},
          "y": {"min": ..., "max": ..., "n": ...}
        }
    k : int
        Number of neighbors for weighting.
    power : float
        IDW power parameter. Set to 0 for uniform averaging of neighbors.
    average_duplicates : bool
        If True, average duplicate (x,y) rows before building the tree.
    """
    print("Applying interpolation with IDW (k={}, power={})".format(k, power))
    x_min, x_max, x_n = grid_params["x"]["min"], grid_params["x"]["max"], grid_params["x"]["n"]
    y_min, y_max, y_n = grid_params["y"]["min"], grid_params["y"]["max"], grid_params["y"]["n"]
    print(grid_params)

    # Average duplicate (x,y) points
    if average_duplicates:
        # only average numeric columns; non-numerics are dropped
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if "x" not in numeric_cols: numeric_cols.append("x")
        if "y" not in numeric_cols: numeric_cols.append("y")
        dfu = (df[numeric_cols]
               .groupby(["x", "y"], as_index=False)
               .mean(numeric_only=True))
    else:
        dfu = df.copy()

    # Build query grid
    xi = np.linspace(x_min, x_max, x_n)
    yi = np.linspace(y_min, y_max, y_n)
    X, Y = np.meshgrid(xi, yi, indexing="xy")
    grid_points = np.column_stack([X.ravel(), Y.ravel()])

    # KDTree on unique points
    pts = dfu[["x", "y"]].to_numpy()
    n_pts = len(pts)
    if n_pts == 0:
        raise ValueError("No input points to interpolate.")

    k_eff = min(k, n_pts)  # in case dataset smaller than k
    tree = KDTree(pts)
    dist, ind = tree.query(grid_points, k=k_eff)

    # Prepare variables to interpolate (numeric, excluding x,y)
    all_numeric = dfu.select_dtypes(include=[np.number]).columns.tolist()
    variables = [c for c in all_numeric if c not in ("x", "y")]
    if not variables:
        raise ValueError("No numeric variables (besides x,y) found to interpolate.")

        # Compute weights (IDW or uniform if power==0)
    if power == 0:
        # uniform weights across k neighbors
        weights = np.full_like(dist, 1.0 / dist.shape[1], dtype=float)
    else:
        # IDW weights; handle exact matches by setting that weight to 1
        with np.errstate(divide='ignore'):
            w = 1.0 / (np.power(dist, power) + 1e-12)
        # If any distance is effectively zero for a row, make that neighbor carry full weight
        zero_rows = np.any(dist < 1e-12, axis=1)
        if np.any(zero_rows):
            # For rows with zeros, zero all weights then set zeros to 1 (if multiple zeros, they’ll share equally)
            w[zero_rows] = 0.0
            zero_mask = dist[zero_rows] < 1e-12
            # Normalize per-row among the zero-distance neighbors (could be >1 if duplicates landed exactly on grid)
            w[zero_rows] = zero_mask / zero_mask.sum(axis=1, keepdims=True)
        # Normalize remaining rows
        row_sums = w.sum(axis=1, keepdims=True)
        # Safeguard in case of any weird numerical issue
        row_sums[row_sums == 0] = 1.0
        weights = w / row_sums

    # Interpolate each variable with the weights
    out = {}
    for var in variables:
        print(f"Interpolating {var} (k={k_eff}, power={power})")
        vals = dfu[var].to_numpy()
        # Gather neighbor values for each grid point and apply weights
        neigh_vals = vals[ind]  # shape (n_grid, k_eff)
        out[var] = np.sum(weights * neigh_vals, axis=1)

    # Return flat DataFrame like your original (x,y alongside all variables)
    out["x"] = grid_points[:, 0]
    out["y"] = grid_points[:, 1]
    interpolated_df = pd.DataFrame(out)

    return interpolated_df


def process_zip(bucket_name, zip_key, benchmark_pb, code_name, version, user_metadata=None, **kwargs):
    output_folder = f"/tmp/{code_name}_{version}/"
    os.makedirs(output_folder, exist_ok=True)

    file_list = []
    file_header = {}  # Now accumulates header per prefix

    # Download and unzip the file
    zip_obj = s3.get_object(Bucket=bucket_name, Key=zip_key)
    # Load the JSON template
    template_key = f"benchmark_templates/{benchmark_pb}.json"
    try:
        response = s3.get_object(Bucket=bucket_name, Key=template_key)
        template_content = response['Body'].read().decode('utf-8')
        template = json.loads(template_content)
        print("template loaded successfully")
    except Exception as e:
        raise ValueError(f"Error loading template {template_key}: {e}")

    with zipfile.ZipFile(BytesIO(zip_obj['Body'].read())) as zip_obj:
        zip_file_list = zip_obj.namelist()
        for file_info in template['files']:
            prefix = file_info['prefix']
            file_type = file_info['file_type']
            expected_structure = file_info

            # Find matching files, even if they're in subdirectories
            matching_files = [
                f for f in zip_file_list
                if os.path.basename(f).startswith(prefix) and f.endswith(f".{file_type}")
            ]
            print(f"number of matching files for {prefix} {len(matching_files)}")
            for file_name in matching_files:
                # Read and validate file
                with zip_obj.open(file_name) as file:
                    file_content = file.read().decode('utf-8')

                    # Only extract header once per prefix (e.g., first matching file)
                    if prefix not in file_header:
                        file_header = extract_header(file_header, prefix, file_content)

                    df = pd.read_csv(StringIO(file_content), comment='#', sep='\s+')

                    # Validate columns
                    var_list = expected_structure['var_list']
                    expected_columns = [var['name'].lower() for var in
                                        var_list]  # Convert expected columns to lowercase
                    df_columns_lowercase = [col.lower() for col in df.columns]  # Convert actual columns to lowercase

                    if df_columns_lowercase != expected_columns:
                        warnings.warn(
                            f"File {os.path.basename(file_name)} does not match the expected structure. Expected columns: {expected_columns}, found columns: {df_columns_lowercase}")
                        continue

                    # Force DataFrame column names to lowercase
                    df.columns = df.columns.str.lower()

                    if "grid" in expected_structure:
                        df = interpolate_data(df, expected_structure['grid'])
                    # Save as Parquet
                    output_path = os.path.join(output_folder,
                                               f"{os.path.splitext(os.path.basename(file_name))[0]}.parquet")
                    df.to_parquet(output_path, index=False)

                # Upload the Parquet file to the main bucket with the benchmark_pb structure
                target_key = f"public_ds/{benchmark_pb}/{code_name}_{version}/{os.path.basename(output_path)}"
                s3.upload_file(output_path, "benchmark-vv-data", target_key, ExtraArgs={"Metadata": user_metadata})
                file_list.append(file_name)
                os.remove(output_path)

    # Save metadata as JSON and upload it
    metadata = {**file_header, "processed_files": file_list}
    metadata_path = os.path.join(output_folder, "metadata.json")
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=4)

    s3.upload_file(metadata_path, "benchmark-vv-data", f"public_ds/{benchmark_pb}/{code_name}_{version}/metadata.json",
                   ExtraArgs={"Metadata": user_metadata})


def handler(event, context):
    try:
        print(event)
        # for record in event['Records']:
        s3_detail = event.get("s3Event", {}).get("detail", {})
        bucket_name = s3_detail.get("bucket", {}).get("name", "unknown")
        zip_key = s3_detail.get("object", {}).get("key", "unknown")

        # Extract metadata from the uploaded file
        response = s3.head_object(Bucket=bucket_name, Key=zip_key)
        user_metadata = response.get('Metadata', {})
        print(f'Metadata: {user_metadata}')

        user_id = user_metadata.get("userid")
        file_id = os.path.basename(zip_key)
        if not user_id:
            print(f'No userid found for {zip_key}')
            return {"error": "userId not found in S3 object metadata"}

        # Write initial status to DynamoDB
        timestamp = datetime.utcnow().isoformat() + "Z"  # ISO format with UTC timezone

        table.put_item(
            Item={
                "userId": user_id,
                "fileId": file_id,
                "status": "processing",
                "timestamp": timestamp,  # Add timestamp if available
            }
        )

        # Extract benchmark_pb, code_name, and version from the zip key
        parts = zip_key.split('/')
        benchmark_pb = parts[1]  # e.g., bp1_qd
        zip_name = os.path.basename(zip_key)
        code_name, version = zip_name.rsplit('.', 1)[0].split('_', 1)
        print(f'Processing benchmark {benchmark_pb}, code {code_name}, version {version}')
        try:
            process_zip(bucket_name, zip_key, benchmark_pb, code_name, version, user_metadata)
        except Exception as e:
            print(f"Error processing {zip_key}: {e}")
            if user_id and file_id:
                table.update_item(
                    Key={"userId": user_id, "fileId": file_id},
                    UpdateExpression="SET #status = :status, #error = :error",
                    ExpressionAttributeNames={
                        "#status": "status",
                        "#error": "error",
                    },
                    ExpressionAttributeValues={
                        ":status": "failed",
                        ":error": str(e),
                    },
                )
            return {"error": f"Error processing {zip_key}: {e}"}

        # Update status to "completed"
        table.update_item(
            Key={"userId": user_id, "fileId": file_id},
            UpdateExpression="SET #status = :status",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":status": "completed"},
        )
        return {"status": "completed"}

    except NoCredentialsError:
        return {"error": "AWS credentials not found"}
    except ClientError as e:
        return {"error": str(e)}
