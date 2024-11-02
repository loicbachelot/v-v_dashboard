import os
import json
import boto3
import pandas as pd
from io import StringIO

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

def process_folder(bucket_name, folder_prefix, code_name, version):
    output_folder = f"/tmp/{code_name}_v{version}/"
    os.makedirs(output_folder, exist_ok=True)

    file_list = []
    common_header = None

    # List all files under the uploaded folder
    response = s3.list_objects_v2(Bucket=bucket_name, Prefix=folder_prefix)
    for obj in response.get('Contents', []):
        if obj['Key'].endswith(".dat"):
            # Download the .dat file from S3
            file_content = s3.get_object(Bucket=bucket_name, Key=obj['Key'])['Body'].read().decode('utf-8')

            # Extract the header from the first file
            if common_header is None:
                common_header = extract_header(file_content)

            # Create DataFrame and convert time
            df = pd.read_csv(StringIO(file_content), comment='#', delim_whitespace=True)
            df['years'], df['days'], df['hours'], df['seconds'] = convert_seconds_to_time(df['t'])

            # Determine depth and save to Parquet
            depth = obj['Key'].split('dp')[-1].split('.')[0]
            output_path = os.path.join(output_folder, f"{code_name}_v{version}_{depth}.parquet")
            df.to_parquet(output_path, index=False)

            # Upload the Parquet file to the main bucket
            s3.upload_file(output_path, "benchmark-vv-data", f"{code_name}_v{version}/{os.path.basename(output_path)}")
            file_list.append(obj['Key'])

    # Save metadata as JSON and upload it
    metadata = {"common_header": common_header, "processed_files": file_list}
    metadata_path = os.path.join(output_folder, "metadata.json")
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=4)

    s3.upload_file(metadata_path, "benchmark-vv-data", f"{code_name}_v{version}/metadata.json")

def handler(event, context):
    for record in event['Records']:
        bucket_name = record['s3']['bucket']['name']
        folder_prefix = record['s3']['object']['key'].rstrip('/') + '/'

        # Extract code_name and version from the folder name
        folder_name = folder_prefix.split('/')[-2]
        code_name, version = folder_name.split('_', 1)

        try:
            process_folder(bucket_name, folder_prefix, code_name, version)
        except Exception as e:
            print(f"Error processing {folder_prefix}: {e}")