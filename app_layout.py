import dash_bootstrap_components as dbc
from dash import dcc
from dash import html
import glob


def get_main_page():
    init_list_datasets = glob.glob("./resources/*/*.dat")
    return html.Div(
        id="root",
        children=[
            dbc.Col(
                children=[
                    dbc.Label("Choose what to display"),
                    dcc.Dropdown(
                        id='dataset-choice',
                        options=init_list_datasets,
                        multi=True,
                        value=[],
                    )
                ],
            ),
            dcc.Graph(
                id='graph',
                style={'height': '85vh'},
                animate=False,
                config={"displayModeBar": True,
                        "displaylogo": False,
                        "scrollZoom": True
                        }
            ),
            # invisible div to trigger the updates on change of dataset
            html.Div([
                dcc.Input(
                    id='dataset-update',
                    value=0,
                )
            ], style={'display': 'none'}
            )
        ])
