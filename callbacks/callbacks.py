import html
import json
import dash
import pandas as pd
from callbacks.plots import main_time_plot_dynamic, main_surface_plot_dynamic
from callbacks.utils import get_df, get_upload_df, fetch_group_names_for_benchmark, get_metadata, get_benchmark_params, \
    get_plots_from_json
from dash import html, callback_context, no_update


def get_callbacks(app):
    @app.callback(dash.dependencies.Output('time-series-graph', 'figure'),
                  [
                      dash.dependencies.Input('show-graphs', "n_clicks"),
                      dash.dependencies.Input('submit-button-gc', 'n_clicks'),
                      dash.dependencies.Input('benchmark-params', 'data'),
                      dash.dependencies.Input('file-type-selector', "value"),
                  ],
                  [
                      dash.dependencies.State('dataset-choice', "value"),
                      dash.dependencies.State('receiver-selector', "value"),
                      dash.dependencies.State('url', "search"),
                      dash.dependencies.State('upload-data', "contents"),
                      dash.dependencies.State('upload-data', 'filename'),
                      dash.dependencies.State('surface-plot-type', 'value'),
                  ]
                  )
    def display_plots(ds_update_clicks, gc_nclicks, benchmark_params, file_type_name, dataset_list, receiver,
                      benchmark_id, upload_data, filename, surface_plot_type):
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
        if benchmark_params is None or file_type_name == '':
            print("benchmark_params is not loaded yet.")
            return {
                "data": [],
                "layout": {
                    "title": "Time-Series Graph",
                    "xaxis": {"title": "Time"},
                    "yaxis": {"title": "Value"},
                }
            }
        list_df = []
        plots_list = get_plots_from_json(benchmark_params, file_type_name)
        if ds_update_clicks is not None:
            selected_df = get_df(benchmark_id, dataset_list, receiver)
            upload_df = get_upload_df(upload_data, filename)

            if upload_df is not None:
                list_df.append(upload_df)
            if selected_df is not None:
                list_df.append(selected_df)
            if len(list_df) > 0:
                ds_update = pd.concat(list_df)
            else:
                ds_update = pd.DataFrame()
        else:
            ds_update = pd.DataFrame()

        if file_type_name == 'Tsunami':
            return main_surface_plot_dynamic(ds_update, plots_list, surface_plot_type)
        return main_time_plot_dynamic(ds_update, plots_list)

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
            file_name = eval(triggered[0]['prop_id'].rsplit('.', 1)[0])['index']
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
        Update the dataset selection options based on the benchmark_id in the URL.

        Parameters:
        search (str): Name of the selected benchmark in the url

        Returns:
        list: List of available dataset options.
        """
        datasets = fetch_group_names_for_benchmark(search)
        links = [
            {'label': html.Span([file, html.A(": info", href='#', id={'type': 'file-link', 'index': file})]),
             'value': file}
            for file in datasets or []  # Handle case if dataset_list is None
        ]
        return links

    @app.callback(
        dash.dependencies.Output('benchmark-params', 'data'),
        [dash.dependencies.Input('url', 'search')]
    )
    def load_benchmark_params(search):
        """
        Update the benchmark_params based on the benchmark_id in the URL.

        Parameters:
        search (str): Name of the selected benchmark in the url

        Returns:
        list: List of available files type.
        """
        return get_benchmark_params(search)

    @app.callback(
        dash.dependencies.Output('file-type-selector', 'options'),
        dash.dependencies.Output('file-type-selector', 'value'),
        [dash.dependencies.Input('benchmark-params', 'data')]
    )
    def update_file_type_selector(benchmark_params):
        """
        Update the file type selector based on the benchmark_params.

        Parameters:
        benchmark_params (list): List of available files type.

        Returns:
        list: List of available files type.
        """
        if benchmark_params is None:
            return no_update
        list_files = [file['name'] for file in benchmark_params['files']]
        return list_files, list_files[0]

    @app.callback(
        dash.dependencies.Output('receiver-selector', 'options'),
        dash.dependencies.Output('receiver-selector', 'value'),
        [dash.dependencies.Input('file-type-selector', 'value')],
        [dash.dependencies.State('benchmark-params', 'data')]
    )
    def update_receiver_selector(file_selected, benchmark_params):
        """
        Update the file type selector based on the benchmark_params.

        Parameters:
        benchmark_params (list): List of available files type.

        Returns:
        list: List of available receivers.
        """
        if benchmark_params is None:
            return no_update
        if file_selected is None:
            return no_update
        for file in benchmark_params['files']:
            if file['name'] == file_selected:
                return file['list_of_receivers'], ''
        return no_update