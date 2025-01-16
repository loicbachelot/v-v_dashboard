import os
import json
import zipfile

import boto3
import pandas as pd
from io import StringIO, BytesIO

s3 = boto3.client('s3')


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

    with zipfile.ZipFile(BytesIO(zip_obj['Body'].read())) as zip_file:
        for file_info in template['files']:
            prefix = file_info['prefix']
            file_type = file_info['file_type']
            expected_structure = file_info
            # Match files based on prefix and file type
            matching_files = [f for f in zip_file.namelist() if f.startswith(prefix) and f.endswith(f".{file_type}")]
            for file_name in matching_files:
                # Read and validate file
                with zip_file.open(file_name) as file:
                    file_content = file.read().decode('utf-8')
                    df = pd.read_csv(StringIO(file_content), comment='#', sep='\s+')

                    # Validate columns
                    var_list = expected_structure['var_list']
                    expected_columns = [var['name'] for var in var_list]
                    if list(df.columns) != expected_columns:
                        raise ValueError(f"File {file_name} does not match the expected structure.")
                    # Save as Parquet
                    output_path = os.path.join(output_folder, f"{os.path.splitext(file_name)[0]}.parquet")
                    df.to_parquet(output_path, index=False)
                    # Extract the header from the first .dat file
                    if common_header is None:
                        common_header = extract_header(file_content)

                # Upload the Parquet file to the main bucket with the benchmark_pb structure
                target_key = f"public_ds/{benchmark_pb}/{code_name}_{version}/{os.path.basename(output_path)}"
                s3.upload_file(output_path, "benchmark-vv-data", target_key, ExtraArgs={"Metadata": user_metadata})
                file_list.append(file_name)

    # Save metadata as JSON and upload it
    metadata = {"common_header": common_header, "processed_files": file_list}
    metadata_path = os.path.join(output_folder, "metadata.json")
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=4)

    s3.upload_file(metadata_path, "benchmark-vv-data", f"public_ds/{benchmark_pb}/{code_name}_{version}/metadata.json",
                   ExtraArgs={"Metadata": user_metadata})


def handler(event, context):
    for record in event['Records']:
        bucket_name = record['s3']['bucket']['name']
        zip_key = record['s3']['object']['key']

        # Extract metadata from the uploaded file
        response = s3.head_object(Bucket=bucket_name, Key=zip_key)
        user_metadata = response.get('Metadata', {})
        print(f'Metadata: {user_metadata}')

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
