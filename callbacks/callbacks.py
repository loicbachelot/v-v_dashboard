import dash
import pandas as pd
import os
from callbacks.plots import main_plot
from callbacks.utils import get_df, get_upload_df


def get_callbacks(app):
    @app.callback(dash.dependencies.Output('time-series-graph', 'figure'),
                  dash.dependencies.Input('dataset-value', 'data'),
                  dash.dependencies.Input('submit-button', 'n_clicks'),
                  dash.dependencies.State('year-start', 'value'),
                  dash.dependencies.State('year-end', 'value')
                  )
    def display_timeseries(ds_update, click, year_start, year_end):
        start = 0
        end = 3000
        if year_start is not None and year_end is not None:
            if 0 < year_start < year_end < 3000:
                start = year_start
                end = year_end
        return main_plot(pd.read_json(ds_update, orient='split'), start, end)

    @app.callback(dash.dependencies.Output('dataset-value', 'data'),
                  [dash.dependencies.Input('dataset-choice', "value"),
                   dash.dependencies.Input('depth-selector', "value"),
                   dash.dependencies.Input('upload-data', "contents")],
                  dash.dependencies.State('upload-data', 'filename'),
                  )
    def update_dataset(dataset_list, depth, upload_data, filename):
        list_df = []
        selected_df = get_df(dataset_list, depth)
        upload_df = get_upload_df(upload_data, filename)
        if upload_df is not None:
            list_df.append(upload_df)
        if selected_df is not None:
            list_df.append(selected_df)
        if len(list_df) > 0:
            return pd.concat(list_df).to_json(date_format='iso', orient='split')
        else:
            return pd.DataFrame().to_json(date_format='iso', orient='split')

    @app.callback(dash.dependencies.Output('upload-filename', 'children'),
                  dash.dependencies.Input('upload-data', 'contents'),
                  dash.dependencies.State('upload-data', 'filename'))
    def print_upload_filename(upload_data, filename):
        return filename

    @app.callback(
        dash.dependencies.Output('dataset-choice', 'options'),
        [dash.dependencies.Input('dataset-choice', 'value')]
    )
    def update_dataset_selection(selected_file):
        updated_options = os.listdir("./resources/bp1-qd")
        return updated_options
