import base64
import plotly.express as px
import boto3
import pandas as pd
import io
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Create a global S3 client for reuse across function calls
s3_client = boto3.client('s3')

def get_s3_object(bucket_name, s3_key):
    """Fetch a single S3 object and return a DataFrame."""
    try:
        obj = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        df = pd.read_parquet(io.BytesIO(obj['Body'].read()))
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
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=f"{benchmark_id}/")

        # Use a set to store unique group names
        group_names = set()
        if 'Contents' in response:
            for obj in response['Contents']:
                parts = obj['Key'].split('/')
                if len(parts) > 1:  # Ensure it's a valid path with group name
                    group_names.add(parts[1])  # Add group name to the set

    except Exception as e:
        print(f"Error fetching datasets: {e}")
        group_names = {'no datasets found'}

    return list(group_names)


def get_upload_df(data, filename):
    """
    Convert uploaded data to a DataFrame and add time columns.

    Parameters:
    data (str): Base64 encoded string of the uploaded data.
    filename (str): Name of the uploaded file.

    Returns:
    DataFrame: A pandas DataFrame containing the uploaded data with additional time columns.
    """
    try:
        content_type, content_string = data.split(',')
        decoded = base64.b64decode(content_string)
        df = pd.read_csv(io.StringIO(decoded.decode('utf-8')), comment='#', delim_whitespace=True)
        df['dataset_name'] = filename
        df['years'], df['days'], df['hours'], df['seconds'] = convert_seconds_to_time(df['t'])
        return df
    except Exception as e:
        print(e)
        return None


async def fetch_data_concurrently(bucket_name, list_df, depth_list):
    """Fetch data concurrently from S3."""
    all_data = []

    # Use a ThreadPoolExecutor to handle blocking I/O with pandas
    with ThreadPoolExecutor() as executor:
        loop = asyncio.get_event_loop()
        tasks = []

        # Prepare S3 fetch tasks for all dataset-depth combinations
        for file_name in list_df:
            for depth in depth_list:
                s3_key = f"bp1-qd/{file_name}/{file_name}_bp1-qd_fltst_dp{depth}.parquet"
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
                file_name, depth = list_df[i // len(depth_list)], depth_list[i % len(depth_list)]
                tmp_df['dataset_name'] = f"{file_name}_dp{depth}"
                # tmp_df['years'], tmp_df['days'], tmp_df['hours'], tmp_df['seconds'] = convert_seconds_to_time(
                #     tmp_df['t']
                # )
                all_data.append(tmp_df)

    return pd.concat(all_data) if all_data else None


def get_df(list_df, depth_list):
    """Get a concatenated DataFrame from a list of datasets and depths."""
    if list_df and depth_list:
        return asyncio.run(fetch_data_concurrently('benchmark-vv-data', list_df, depth_list))
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
