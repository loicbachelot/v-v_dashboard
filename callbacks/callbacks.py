import dash
import pandas as pd
from callbacks.plots import main_plot
from callbacks.utils import get_df, get_upload_df, fetch_group_names_for_benchmark


def get_callbacks(app):
    @app.callback(dash.dependencies.Output('time-series-graph', 'figure'),
                  dash.dependencies.Input('dataset-value', 'data'),
                  dash.dependencies.Input('submit-button', 'n_clicks'),
                  dash.dependencies.State('year-start', 'value'),
                  dash.dependencies.State('year-end', 'value'),
                  dash.dependencies.State('time-unit', 'value'),
                  dash.dependencies.State('xaxis-var', 'value')
                  )
    def display_timeseries(ds_update, click, year_start, year_end, time_unit, xaxis_var):
        """
        Update the time-series graph based on user inputs.

        Parameters:
        ds_update (str): JSON string of the dataset.
        click (int): Number of times the submit button has been clicked.
        year_start (int): Start year for the time series.
        year_end (int): End year for the time series.
        time_unit (str): Time unit for the x-axis.
        xaxis_var (str): Variable for the x-axis.

        Returns:
        dict: Figure object for the time-series graph.
        """
        start = 0
        end = 3000
        if year_start is not None and year_end is not None:
            if 0 < year_start < year_end < 3000:
                start = year_start
                end = year_end
        if xaxis_var == 'time':
            xaxis_var = time_unit
        return main_plot(pd.read_json(ds_update, orient='split'), start, end, xaxis_var)

    @app.callback(dash.dependencies.Output('dataset-value', 'data'),
                  [dash.dependencies.Input('dataset-choice', "value"),
                   dash.dependencies.Input('depth-selector', "value"),
                   dash.dependencies.Input('upload-data', "contents")],
                  dash.dependencies.State('upload-data', 'filename'),
                  )
    def update_dataset(dataset_list, depth, upload_data, filename):
        """
        Update the dataset based on user selection and uploaded data.

        Parameters:
        dataset_list (list): List of selected datasets.
        depth (str): Depth selector value.
        upload_data (str): Contents of the uploaded data.
        filename (str): Name of the uploaded file.

        Returns:
        str: JSON string of the concatenated dataset.
        """
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
        """
        Display the filename of the uploaded data.

        Parameters:
        upload_data (str): Contents of the uploaded data.
        filename (str): Name of the uploaded file.

        Returns:
        str: Filename of the uploaded file.
        """
        return filename

    @app.callback(
        dash.dependencies.Output('dataset-choice', 'options'),
        [dash.dependencies.Input('dataset-choice', 'value')]
    )
    def update_dataset_selection(selected_file):
        """
        Update the dataset selection options based on the selected file.

        Parameters:
        selected_file (str): Name of the selected file.

        Returns:
        list: List of available dataset options.
        """
        benchmark_id = "bp1-qd"
        return fetch_group_names_for_benchmark(benchmark_id)
