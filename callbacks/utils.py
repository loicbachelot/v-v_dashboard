import callbacks.config as config
import pandas as pd
import glob


def convert_seconds_to_time(seconds):
    years = seconds / (365.25 * 24 * 3600)
    days = (seconds / (24 * 3600))
    hours = seconds / 3600
    seconds = seconds
    return years, days, hours, seconds


def get_ds_in_folder(folder_path):
    ds_names = glob.glob(f"{folder_path}/*/")
    return ds_names


def get_df(list_df, depth_list):
    if len(list_df) > 0 and len(depth_list) > 0:
        all_ds = []
        for file_name in list_df:
            for depth in depth_list:
                ds_path = glob.glob(f"./resources/bp1-qd/{file_name}/*{depth}.dat")[0]
                tmp_df = pd.read_csv(ds_path, comment='#', delim_whitespace=True)
                tmp_df['dataset_name'] = file_name + "_dp" + depth
                tmp_df['years'], tmp_df['days'], tmp_df['hours'], tmp_df['seconds'] = convert_seconds_to_time(tmp_df['t'])
                all_ds.append(tmp_df)
        config.df = pd.concat(all_ds)
    else:
        config.df = pd.DataFrame()
    return 0


def generate_color_mapping(datasets):
    color_mapping = {}
    colors = ['red', 'blue', 'green', 'purple', 'orange', 'cyan']  # You can add more colors as needed
    for i, dataset in enumerate(datasets):
        color_mapping[dataset] = colors[i % len(colors)]
    return color_mapping
