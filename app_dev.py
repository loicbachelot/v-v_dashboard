import dash
import dash_bootstrap_components as dbc
import app_layout
from callbacks.callbacks import get_callbacks

app = dash.Dash(external_stylesheets=[dbc.themes.CERULEAN])

server = app.server

app.layout = app_layout.get_main_page()

get_callbacks(app)


if __name__ == '__main__':
    app.run_server(debug=True)
