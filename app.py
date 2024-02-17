import dash
import dash_bootstrap_components as dbc
import glob
import app_layout
from callbacks.callbacks import get_callbacks

app = dash.Dash(external_stylesheets=[dbc.themes.CERULEAN])

server = app.server

list_datasets = glob.glob("./resources/*.csv")

app.layout = app_layout.get_main_page(list_datasets)

get_callbacks(app)


if __name__ == '__main__':
    app.run_server(debug=True)
