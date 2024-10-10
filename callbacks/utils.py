import base64
import io
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


def get_ds_in_folder(folder_path):
    """
    Get the names of datasets in a specified folder.

    Parameters:
    folder_path (str): Path to the folder containing datasets.

    Returns:
    list: List of dataset names.
    """
    ds_names = glob.glob(f"{folder_path}/*/")
    return ds_names


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
        all_ds = []
        for file_name in list_df:
            for depth in depth_list:
                ds_path = glob.glob(f"./resources/bp1-qd/{file_name}/*{depth}.dat")[0]
                tmp_df = pd.read_csv(ds_path, comment='#', delim_whitespace=True)
                tmp_df['dataset_name'] = file_name + "_dp" + depth
                tmp_df['years'], tmp_df['days'], tmp_df['hours'], tmp_df['seconds'] = convert_seconds_to_time(tmp_df['t'])
                all_ds.append(tmp_df)
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
