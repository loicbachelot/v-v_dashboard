import os
import json
import warnings
import zipfile
from datetime import datetime

import boto3
import pandas as pd
from io import StringIO, BytesIO

from scipy.interpolate import NearestNDInterpolator, griddata
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


def extract_header(content):
    """Extract and parse the common header from a .dat file."""
    header_data = {}
    for line in content.splitlines():
        if line.startswith("# File:"):
            continue
        if line.startswith('#'):
            if '=' in line:
                key, value = line[2:].strip().split('=', 1)
                header_data[key.strip()] = value.strip()
            else:
                header_data.setdefault('comments', []).append(line[2:].strip())
    return header_data


def interpolate_data(df, grid_params):
    """Apply interpolation for all variables in the dataframe."""
    print(f"Applying interpolation")

    x_min, x_max, x_n = grid_params["x"]["min"], grid_params["x"]["max"], grid_params["x"]["n"]
    y_min, y_max, y_n = grid_params["y"]["min"], grid_params["y"]["max"], grid_params["y"]["n"]

    print(grid_params)

    # Create a regular grid
    x_grid = np.linspace(x_min, x_max, x_n)
    y_grid = np.linspace(y_min, y_max, y_n)
    x_mesh, y_mesh = np.meshgrid(x_grid, y_grid)

    variables = [col for col in df.columns if col not in ["x", "y"]]

    interpolated_data = {"x": x_mesh.flatten(), "y": y_mesh.flatten()}
    # Interpolate all variables values onto the grid
    for var in variables:
        print(f"interpolating {var}")
        var_grid = griddata(
            (df['x'], df['y']),  # Input points
            df[var],  # Input values
            (x_mesh, y_mesh),  # Grid to interpolate onto
            method='linear'  # Interpolation method ('linear', 'nearest', 'cubic')
        )

        # Extrapolate missing values using nearest neighbor
        valid_mask = ~np.isnan(var_grid)  # Mask of valid (non-NaN) values
        valid_points = np.column_stack((x_mesh[valid_mask], y_mesh[valid_mask]))  # Valid (x, z) points
        valid_values = var_grid[valid_mask]  # Valid v-disp values

        # Create a nearest neighbor interpolator
        nearest_interp = NearestNDInterpolator(valid_points, valid_values)

        # Fill missing values by extrapolating
        var_grid_filled = np.where(
            np.isnan(var_grid),  # Condition: Where values are NaN
            nearest_interp(x_mesh, y_mesh),  # Fill with nearest neighbor values
            var_grid  # Keep original values where not NaN
        )
        interpolated_data[var] = var_grid_filled.flatten()

    # Create a new DataFrame
    interpolated_df = pd.DataFrame(interpolated_data)
    return interpolated_df


def process_zip(bucket_name, zip_key, benchmark_pb, code_name, version, user_metadata=None, **kwargs):
    output_folder = f"/tmp/{code_name}_{version}/"
    os.makedirs(output_folder, exist_ok=True)

    file_list = []
    common_header = None

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
                    # Extract the header from the first .dat file
                    if common_header is None:
                        common_header = extract_header(file_content)

                # Upload the Parquet file to the main bucket with the benchmark_pb structure
                target_key = f"public_ds/{benchmark_pb}/{code_name}_{version}/{os.path.basename(output_path)}"
                s3.upload_file(output_path, "benchmark-vv-data", target_key, ExtraArgs={"Metadata": user_metadata})
                file_list.append(file_name)
                os.remove(output_path)

    # Save metadata as JSON and upload it
    metadata = {"common_header": common_header, "processed_files": file_list}
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
