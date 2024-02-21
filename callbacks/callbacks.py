import sys
import dash
import pandas as pd
import os
import callbacks.config as config
from callbacks.plots import main_plot
from callbacks.utils import get_df, get_ds_in_folder


def get_callbacks(app):
    @app.callback(dash.dependencies.Output('time-series-graph', 'figure'),
                  dash.dependencies.Input('dataset-update', "value")
                  )
    def display_accuracy(ds_update):
        return main_plot(config.df)

    @app.callback(dash.dependencies.Output('dataset-update', 'value'),
                  [dash.dependencies.Input('dataset-choice', "value"),
                   dash.dependencies.Input('depth-selector', "value")]
                  )
    def update_dataset(dataset_list, depth):
        get_df(dataset_list, depth)

    @app.callback(
        dash.dependencies.Output('dataset-choice', 'options'),
        [dash.dependencies.Input('dataset-choice', 'value')]
    )
    def update_dataset_selection(selected_file):
        updated_options = os.listdir("./resources/bp1-qd")
        return updated_options
