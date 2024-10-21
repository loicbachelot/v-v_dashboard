import base64
import io
import boto3
import pandas as pd
import glob
import plotly.express as px


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
        s3_client = boto3.client('s3')
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


def get_df(list_df, depth_list):
    """
    Get a concatenated DataFrame from a list of datasets and depths.

    Parameters:
    list_df (list): List of dataset names.
    depth_list (list): List of depth values.

    Returns:
    DataFrame: A pandas DataFrame containing the concatenated datasets.
    """
    if len(list_df) > 0 and len(depth_list) > 0:
        s3_client = boto3.client('s3')
        bucket_name = 'benchmark-vv-data'
        all_ds = []
        for file_name in list_df:
            for depth in depth_list:
                s3_key = f"bp1-qd/{file_name}/{file_name}_bp1-qd_fltst_dp{depth}.dat" # TODO: Change this to the correct path
                try:
                    obj = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
                    tmp_df = pd.read_csv(io.BytesIO(obj['Body'].read()), comment='#', delim_whitespace=True)
                    tmp_df['dataset_name'] = file_name + "_dp" + depth
                    tmp_df['years'], tmp_df['days'], tmp_df['hours'], tmp_df['seconds'] = convert_seconds_to_time(
                        tmp_df['t'])
                    all_ds.append(tmp_df)
                except Exception as e:
                    print(f"Error fetching {s3_key}: {e}")
        df = pd.concat(all_ds)
        return df
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
