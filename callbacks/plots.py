import plotly.graph_objects as go
from plotly.subplots import make_subplots
from callbacks.utils import generate_color_mapping


def main_plot(df):
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
            fig.add_trace(go.Scatter(x=group['years'], y=group['slip'], mode='lines', legendgroup=dataset_name,
                                     line=dict(color=color), name=dataset_name), row=1, col=1)
            fig.add_trace(go.Scatter(x=group['years'], y=group['slip_rate'], mode='lines', legendgroup=dataset_name,
                                     line=dict(color=color), name=dataset_name, showlegend=False), row=2, col=1)
            fig.add_trace(go.Scatter(x=group['years'], y=group['shear_stress'], mode='lines', legendgroup=dataset_name,
                                     line=dict(color=color), name=dataset_name, showlegend=False), row=1, col=2)
            fig.add_trace(go.Scatter(x=group['years'], y=group['state'], mode='lines', legendgroup=dataset_name,
                                     line=dict(color=color), name=dataset_name, showlegend=False), row=2, col=2)

        # Update layout
        fig.update_layout(title='Variables over Time', showlegend=True, height=1000)
        fig.update_xaxes(title_text='Years', matches='x')
    except Exception as e:
        fig = make_subplots(rows=2, cols=2, shared_xaxes=True,
                            subplot_titles=['Slip', 'Slip Rate', 'Shear Stress', 'State'],
                            vertical_spacing=0.08, horizontal_spacing=0.1)
        fig.add_trace(go.Scatter(x=[0, 1, 2, 3], y=[0, 1, 2, 3], mode='lines'), row=1, col=1)
        fig.add_trace(go.Scatter(x=[0, 1, 2, 3], y=[0, 1, 2, 3], mode='lines'), row=2, col=1)
        fig.add_trace(go.Scatter(x=[0, 1, 2, 3], y=[0, 1, 2, 3], mode='lines'), row=1, col=2)
        fig.add_trace(go.Scatter(x=[0, 1, 2, 3], y=[0, 1, 2, 3], mode='lines'), row=2, col=2)
    return fig
