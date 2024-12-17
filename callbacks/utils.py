import base64
import json
import urllib
import plotly.express as px
import boto3
import pandas as pd
import io
import asyncio
from concurrent.futures import ThreadPoolExecutor
import awswrangler as wr
from dash import html

# Create a global S3 client for reuse across function calls
s3_client = boto3.client('s3')

# Helper function to parse the benchmark_id from the URL
def parse_benchmark_id(search):
    query_params = urllib.parse.parse_qs(search.lstrip('?'))
    return query_params.get('benchmark_id', [''])[0]  # Return first value or empty string


def get_s3_object(bucket_name, s3_key):
    """Fetch a single S3 object and return a DataFrame."""
    try:
        df = wr.s3.read_parquet(f"s3://{bucket_name}/{s3_key}")
        return df

    except Exception as e:
        print(f"Error fetching {s3_key}: {e}")
        return None

def convert_seconds_to_time(seconds):
    """
    Convert a time duration from seconds to years, days, hours, and seconds.

    Parameters:
    seconds (int): Time duration in seconds.

    Returns:
    tuple: A tuple containing years, days, hours, and seconds.
    """
    years = seconds / (365.25 * 24 * 3600)
    days = (seconds / (24 * 3600))
    hours = seconds / 3600
    seconds = seconds
    return years, days, hours, seconds


def fetch_group_names_for_benchmark(benchmark_id):
    try:
        bucket_name = 'benchmark-vv-data'
        # List all objects with the prefix matching the benchmark ID
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=f"public_ds/{parse_benchmark_id(benchmark_id)}/")
        # Use a set to store unique group names
        group_names = set()
        if 'Contents' in response:
            for obj in response['Contents']:
                parts = obj['Key'].split('/')
                if len(parts[2]) > 1:  # Ensure it's a valid path with group name
                    group_names.add(parts[2])  # Add group name to the set
        result = sorted(list(group_names))

    except Exception as e:
        print(f"Error fetching datasets: {e}")
        result = {'no datasets found'}
    return result


def get_upload_df(data, filename):
    """
    Convert uploaded data to a DataFrame and add time columns.

    Parameters:
    data (str): Base64 encoded string of the uploaded data.
    filename (str): Name of the uploaded file.

    Returns:
    DataFrame: A pandas DataFrame containing the uploaded data with additional time columns.
    """
    if data is None:
        return None
    try:
        content_type, content_string = data.split(',')
        decoded = base64.b64decode(content_string)
        df = pd.read_csv(io.StringIO(decoded.decode('utf-8')), comment='#', delim_whitespace=True)
        df['dataset_name'] = filename
        df['years'], df['days'], df['hours'], df['seconds'] = convert_seconds_to_time(df['t'])
        return df
    except Exception as e:
        print(f"Error reading uploaded data: {e}")
        return None


async def fetch_data_concurrently(bucket_name, benchmark_id, list_df, depth):
    """Fetch data concurrently from S3."""
    all_data = []

    # Use a ThreadPoolExecutor to handle blocking I/O with pandas
    with ThreadPoolExecutor() as executor:
        loop = asyncio.get_event_loop()
        tasks = []

        # Prepare S3 fetch tasks for all dataset-depth combinations
        for file_name in list_df:
            s3_key = f"public_ds/{benchmark_id}/{file_name}/{file_name}_{depth}.parquet"
            tasks.append(
                loop.run_in_executor(
                    executor, get_s3_object, 'benchmark-vv-data', s3_key
                )
            )

        # Collect results as they complete
        results = await asyncio.gather(*tasks)

        # Process valid DataFrames
        for i, tmp_df in enumerate(results):
            if tmp_df is not None:
                file_name = list_df[i]
                tmp_df['dataset_name'] = f"{file_name}_dp{depth}"
                all_data.append(tmp_df)

    return pd.concat(all_data) if all_data else None


def get_df(benchmark_id, list_df, depth):
    """Get a concatenated DataFrame from a list of datasets and depths."""
    if list_df and depth:
        return asyncio.run(fetch_data_concurrently('benchmark-vv-data', parse_benchmark_id(benchmark_id), list_df, depth))
    else:
        return None


def generate_color_mapping(datasets):
    """
    Generate a color mapping for a list of datasets.

    Parameters:
    datasets (list): List of dataset names.

    Returns:
    dict: A dictionary mapping dataset names to colors.
    """
    color_mapping = {}
    colors = px.colors.qualitative.D3
    for i, dataset in enumerate(datasets):
        color_mapping[dataset] = colors[i % len(colors)]
    return color_mapping

def get_metadata(benchmark_id, dataset_name):
    """
    Get metadata for a dataset.

    Parameters:
    benchmark_id (str): The benchmark ID.
    dataset_name (str): The name of the dataset.

    Returns:
    dict: Metadata for the dataset.
    """
    try:
        bucket_name = 'benchmark-vv-data'
        s3_key = f"public_ds/{parse_benchmark_id(benchmark_id)}/{dataset_name}/metadata.json"
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        metadata = response['Body'].read().decode('utf-8')
        return render_json(json.loads(metadata))
    except Exception as e:
        print(f"Error fetching metadata: {e}")
        return None


# Recursive function to render JSON fields dynamically
def render_json(data):
    if isinstance(data, dict):
        return html.Ul([
            html.Li([html.B(f"{key}: "), render_json(value)])
            for key, value in data.items()
        ])
    elif isinstance(data, list):
        return html.Ul([html.Li(render_json(item)) for item in data])
    else:
        return html.Span(str(data))