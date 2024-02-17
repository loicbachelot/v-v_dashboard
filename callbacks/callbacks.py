import sys
import dash
import pandas as pd
import callbacks.config as config
from callbacks.plots import main_plot
from callbacks.utils import get_df


def get_callbacks(app):
    @app.callback(dash.dependencies.Output('graph', 'figure'),
                  dash.dependencies.Input('dataset-update', "value")
                  )
    def display_accuracy(ds_update):
        return main_plot(config.df)

    @app.callback(dash.dependencies.Output('dataset-update', 'value'),
                  dash.dependencies.Input('dataset-choice', "value")
                  )
    def update_dataset(dataset_change):
        get_df(dataset_change)
