import plotly.graph_objects as go
from plotly.subplots import make_subplots
from callbacks.utils import generate_color_mapping


def main_plot(df, year_start, year_end, x_unit='years'):
    """
    Generate a main plot with subplots for Slip, Slip Rate, Shear Stress, and State.

    Parameters:
    df (pd.DataFrame): DataFrame containing the dataset.
    year_start (int): Start year for the time series.
    year_end (int): End year for the time series.
    x_unit (str): Time unit for the x-axis. Default is 'years'.

    Returns:
    go.Figure: Plotly figure object with the subplots.
    """
    try:
        # Get unique datasets in the file
        datasets = df['dataset_name'].unique()

        # Generate color mapping for each dataset
        color_mapping = generate_color_mapping(datasets)
        fig = make_subplots(rows=2, cols=2, shared_xaxes=True,
                            subplot_titles=['Slip', 'Slip Rate', 'Shear Stress', 'State'],
                            vertical_spacing=0.08, horizontal_spacing=0.1)
        for dataset_name, group in df.groupby('dataset_name'):
            color = color_mapping[dataset_name]

            # Add traces for each variable
            fig.add_trace(go.Scatter(x=group[x_unit], y=group['slip'], mode='lines', legendgroup=dataset_name,
                                     line=dict(color=color), name=dataset_name), row=1, col=1)
            fig.add_trace(go.Scatter(x=group[x_unit], y=group['slip_rate'], mode='lines', legendgroup=dataset_name,
                                     line=dict(color=color), name=dataset_name, showlegend=False), row=1, col=2)
            fig.add_trace(
                go.Scatter(x=group[x_unit], y=group['shear_stress'], mode='lines', legendgroup=dataset_name,
                           line=dict(color=color), name=dataset_name, showlegend=False), row=2, col=1)
            fig.add_trace(go.Scatter(x=group[x_unit], y=group['state'], mode='lines', legendgroup=dataset_name,
                                     line=dict(color=color), name=dataset_name, showlegend=False), row=2, col=2)

        # Update layout
        fig.update_xaxes(title_text=x_unit, matches='x', row=2)
        fig.update_yaxes(title_text="Slip (m)", row=1, col=1)
        fig.update_yaxes(title_text="Slip rate (log10 m/s)", row=1, col=2)
        fig.update_yaxes(title_text="Shear stress (MPa)", row=2, col=1)
        fig.update_yaxes(title_text="State (log10 s)", row=2, col=2)

        if x_unit == 'seconds':
            time_start = year_start * 60 * 60 * 24 * 365
            time_end = year_end * 60 * 60 * 24 * 365
        elif x_unit == 'hours':
            time_start = year_start * 24 * 365
            time_end = year_end * 24 * 365
        elif x_unit == 'days':
            time_start = year_start * 365
            time_end = year_end * 365
        elif x_unit == 'years':
            time_start = year_start
            time_end = year_end
        else:
            time_start = group[x_unit].min()
            time_end = group[x_unit].max()
        fig.update_layout(title=f'Variables over {x_unit}', showlegend=True, xaxis=dict(range=[time_start, time_end]))

    except Exception as e:
        fig = make_subplots(rows=2, cols=2, shared_xaxes=True,
                            subplot_titles=['Slip', 'Slip Rate', 'Shear Stress', 'State'],
                            vertical_spacing=0.04, horizontal_spacing=0.05)
        fig.add_trace(go.Scatter(x=[0, 1, 2, 3], y=[0, 1, 2, 3], mode='lines'), row=1, col=1)
        fig.add_trace(go.Scatter(x=[0, 1, 2, 3], y=[0, 1, 2, 3], mode='lines'), row=2, col=1)
        fig.add_trace(go.Scatter(x=[0, 1, 2, 3], y=[0, 1, 2, 3], mode='lines'), row=1, col=2)
        fig.add_trace(go.Scatter(x=[0, 1, 2, 3], y=[0, 1, 2, 3], mode='lines'), row=2, col=2)
    return fig
