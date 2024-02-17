import callbacks.config as config
import pandas as pd


def get_df(list_df):
    if len(list_df) > 0:
        all_ds = []
        for path in list_df:
            tmp_df = pd.read_csv(path, parse_dates=['time'])
            tmp_df['dataset_name'] = path
            all_ds.append(tmp_df)
        config.df = pd.concat(all_ds)
    else:
        config.df = pd.DataFrame()
    return 0
