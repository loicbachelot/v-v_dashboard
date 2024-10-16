import dash
import dash_bootstrap_components as dbc
import app_layout
from callbacks.callbacks import get_callbacks
import json
import dash_auth


app = dash.Dash(external_stylesheets=[dbc.themes.CERULEAN])

#
# with open('./resources/login.json', 'r') as f:
#     pswd = json.load(f)
#
# auth = dash_auth.BasicAuth(
#     app,
#     pswd
# )

server = app.server

app.layout = app_layout.get_main_page()

get_callbacks(app)


if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=8081)
