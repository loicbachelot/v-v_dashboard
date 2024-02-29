import dash_bootstrap_components as dbc
from dash import dcc
from dash import html
import os


def get_main_page():
    init_list_datasets = os.listdir("./resources/bp1-qd")
    return html.Div(
        id="root",
        children=[
            dbc.Navbar(
                [
                    dbc.Col(
                        html.A(href="https://cascadiaquakes.org/", children=[
                            html.Img(
                                src=r'https://cascadiaquakes.org/wp-content/uploads/2023/10/Crescent-Logos-Horizontal-White-230x62.png'),
                        ]),
                        width={"size": 4, "offset": 1},
                    ),
                    dbc.Col(
                        html.H1("V&V Dashboard", style={
                            'textAlign': 'center',
                            'color': 'white'
                        }),
                        width={"size": 4, "offset": 0}
                    ),
                ],
                color="#26505A",
                dark=True,
                style={
                    'marginBottom': '1rem',
                }
            ),
            dbc.Container(
                id="app-container",
                fluid=True,
                children=[
                    dbc.Row(
                        children=[
                            dbc.Col(
                                [
                                    html.H3("Control panel", style={
                                        'textAlign': 'center',
                                        'color': 'black'
                                    }),
                                    dcc.Tabs(id="tabs-example-graph", value='tab-dataset', children=[
                                        dcc.Tab(label='Dataset selection', value='tab-dataset', children=[
                                            dbc.Row(
                                                children=[
                                                    dbc.Col(
                                                        children=[
                                                            dbc.Label("Dataset choice"),
                                                            dbc.Checklist(
                                                                id='dataset-choice',
                                                                options=init_list_datasets,
                                                                value=[],
                                                            ),
                                                        ],
                                                    ),
                                                    dbc.Col(
                                                        children=[
                                                            dbc.Label("Choose the depth"),
                                                            dbc.Checklist(
                                                                id='depth-selector',
                                                                options=["000", "025", "050", "075", "100",
                                                                         "125", "150", "175", "200",
                                                                         "250", "350"],
                                                                value=[],
                                                            ),
                                                        ],
                                                    ),
                                                ]
                                            ),
                                            dbc.Row(
                                                children=[
                                                    dbc.Col(children=[
                                                        dcc.Upload(id='upload-data',
                                                                   children=[dbc.Button('Upload File', color="secondary")],
                                                                   multiple=False,
                                                                   style={'margin': '10px'}),
                                                        dbc.Button('Upload documentation', id="upload-doc",
                                                                   color="secondary", style={'margin': '10px'}),
                                                        html.Div([html.H5("Uploaded file:", style={'color': '#000000'}),
                                                                  html.P(id="upload-filename")])
                                                        ]
                                                    )
                                                ]
                                            ),
                                        ]),
                                        dcc.Tab(label='Graph control', value='tab-graphcontrol',
                                                children=[
                                                        dbc.Row(
                                                            children=[
                                                                dbc.Col(children=[
                                                                    dbc.Label("Choose x axis variable"),
                                                                    dbc.Select(
                                                                        id="xaxis-var",
                                                                        options=[
                                                                            {"label": "Time", "value": "time"},
                                                                            {"label": "Slip", "value": "slip"},
                                                                            {"label": "Slip Rate", "value": "slip_rate"},
                                                                            {"label": "Shear Stress", "value": "shear_stress"},
                                                                            {"label": "State", "value": "state"}
                                                                        ],
                                                                        value="time"
                                                                    ),
                                                                    dbc.Label("time unit"),
                                                                    dbc.Select(
                                                                        id="time-unit",
                                                                        options=[
                                                                            {"label": "year", "value": "years"},
                                                                            {"label": "days", "value": "days"},
                                                                            {"label": "hours", "value": "hours"},
                                                                            {"label": "seconds", "value": "seconds"}
                                                                        ],
                                                                        value="years"
                                                                    ),
                                                                    dbc.Label(
                                                                        "Choose the period to display in years"),
                                                                    dbc.Input(type="number", min=0, max=3000, step=1,
                                                                              id="year-start", placeholder="start",
                                                                              style={'marginBottom': '10px',
                                                                                     'marginLeft': '10px'}),
                                                                    dbc.Input(type="number", min=0, max=3000, step=1,
                                                                              id="year-end", placeholder="end",
                                                                              style={'marginBottom': '10px',
                                                                                     'marginLeft': '10px'}
                                                                              ),
                                                                    dbc.Button("submit",
                                                                               id='submit-button',
                                                                               n_clicks=0,
                                                                               color="primary",
                                                                               style={'marginBottom': '10px',
                                                                                      'marginLeft': '10px'}

                                                                               ),
                                                                    ]
                                                                )
                                                            ],
                                                        )
                                                    ]
                                                ),
                                            ]
                                        ),
                                ],
                                align="start",
                                width=3,
                            ),
                            dbc.Col([
                                dcc.Loading(id="ls-loading-2", children=[
                                    dcc.Graph(
                                        id='time-series-graph',
                                        style={'responsive': True,
                                               'width': '100%',
                                               'height': '90vh'},
                                        animate=False,
                                        config={"displayModeBar": True,
                                                "displaylogo": False,
                                                "scrollZoom": True
                                                }
                                    ),
                                ], type="default")
                            ],
                                align="start",
                                width=9)
                        ])
                ]),
            # stor user's dataset
            dcc.Store(id='dataset-value')
        ])
