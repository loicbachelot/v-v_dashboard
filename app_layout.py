import dash_bootstrap_components as dbc
from dash import dcc
from dash import html


def get_main_page(list_datasets):
    return html.Div(
        id="root",
        children=[
            dbc.Col(
                children=[
                    dbc.Label("Choose what to display"),
                    dcc.Dropdown(
                        id='dataset-choice',
                        options=[{"label": label, "value": label} for label in list_datasets],
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
