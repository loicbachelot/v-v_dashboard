import html
import json
import dash
import pandas as pd
from callbacks.plots import main_plot
from callbacks.utils import get_df, get_upload_df, fetch_group_names_for_benchmark, get_metadata
from dash import html, callback_context


def get_callbacks(app):
    @app.callback(dash.dependencies.Output('time-series-graph', 'figure'),
                  [
                      dash.dependencies.Input('show-graphs', "n_clicks"),
                      dash.dependencies.Input('submit-button', 'n_clicks')
                  ],
                  [
                      dash.dependencies.State('dataset-choice', "value"),
                      dash.dependencies.State('depth-selector', "value"),
                      dash.dependencies.State('url', "search"),
                      dash.dependencies.State('upload-data', "contents"),
                      dash.dependencies.State('upload-data', 'filename'),
                      dash.dependencies.State('year-start', 'value'),
                      dash.dependencies.State('year-end', 'value'),
                      dash.dependencies.State('time-unit', 'value'),
                ]
                  )
    def display_timeseries(ds_update_clicks, click, dataset_list, depth, benchmark_id, upload_data, filename,
                           year_start, year_end, time_unit):
        """
        Update the time-series graph based on user inputs.

        Parameters:
        ds_update (str): JSON string of the dataset.
        click (int): Number of times the submit button has been clicked.
        year_start (int): Start year for the time series.
        year_end (int): End year for the time series.
        time_unit (str): Time unit for the x-axis.

        Returns:
        dict: Figure object for the time-series graph.
        """
        list_df = []
        selected_df = get_df(benchmark_id, dataset_list, depth)
        upload_df = get_upload_df(upload_data, filename)
        if upload_df is not None:
            list_df.append(upload_df)
        if selected_df is not None:
            list_df.append(selected_df)
        if len(list_df) > 0:
            ds_update = pd.concat(list_df)
        else:
            ds_update =  pd.DataFrame()

        start = 0
        end = 3000
        if year_start is not None and year_end is not None:
            if 0 < year_start < year_end < 3000:
                start = year_start
                end = year_end
        xaxis_var = time_unit
        return main_plot(ds_update, start, end, xaxis_var)

    ### Callback 1: Generate Links Based on Dataset Choice and Benchmark ID
    @app.callback(
        dash.dependencies.Output('links-container', 'children'),
        dash.dependencies.Input('show-graphs', 'n_clicks'),
        dash.dependencies.State('dataset-choice', 'value'),
        prevent_initial_call=True
    )
    def update_links(show_graph_update, dataset_list):
        # Generate the links dynamically
        links = [
            html.Div(
                children=[
                    html.Span("Metadata: "),
                    html.A(file, href='#', id={'type': 'file-link', 'index': file}),
                ],
                style={'margin-bottom': '10px'}
            )
            for file in dataset_list or []  # Handle case if dataset_list is None
        ]
        return links

    ### Callback 2: Handle Modal Open/Close Logic
    @app.callback(
        dash.dependencies.Output('popup-content', 'children'),
        dash.dependencies.Output('popup-modal', 'is_open'),
        dash.dependencies.Input({'type': 'file-link', 'index': dash.dependencies.ALL}, 'n_clicks'),
        dash.dependencies.Input('close-popup', 'n_clicks'),
        dash.dependencies.State('popup-modal', 'is_open'),
        dash.dependencies.State('url', 'search'),
        prevent_initial_call=True
    )
    def handle_modal(file_clicks, close_click, is_open, benchmark_id):
        triggered = callback_context.triggered
        # Debug: Check what triggered the callback
        if not triggered:
            return "", False  # No valid trigger, return modal closed.

        # Check if a file link was clicked
        if "file-link" in triggered[0]['prop_id'] and triggered[0]['value']:
            file_name = eval(triggered[0]['prop_id'].split('.')[0])['index']
            # Fetch and format metadata
            metadata = get_metadata(benchmark_id, file_name)
            return metadata, True  # Open modal with metadata

        # Close modal if the close button was clicked
        return "", False




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
        [dash.dependencies.Input('url', 'search')]
    )
    def update_dataset_selection(search):
        """
        Update the dataset selection options based on the benchmark_id in teh URL.

        Parameters:
        selected_file (str): Name of the selected file.

        Returns:
        list: List of available dataset options.
        """
        return fetch_group_names_for_benchmark(search)
