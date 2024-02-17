import plotly.express as px


def main_plot(df):
    try:
        fig = px.line(df, x="time", y='value', color='dataset_name',
                      hover_data={"time": "|%B %d, %Y"})
    except:
        fig = px.line(x=[0, 1, 2, 3], y=[0, 1, 2, 3])
    return fig
