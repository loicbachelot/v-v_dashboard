
from callbacks.utils import generate_color_mapping
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from plotly_resampler import FigureResampler


def main_plot_dynamic(df, variable_list):
    """
    Generate a dynamic plot with subplots based on a list of variable dictionaries.

    Parameters:
    df (pd.DataFrame): DataFrame containing the dataset.
    year_start (int): Start year for the time series.
    year_end (int): End year for the time series.
    variable_list (list): List of dictionaries with keys 'name', 'unit', and 'description'.
    x_unit (str): Time unit for the x-axis. Default is 'seconds'.

    Returns:
    FigureResampler: Plotly figure object with dynamic resampling enabled.
    """
    try:
        # Calculate the number of rows needed for a 2-column layout
        num_vars = len(variable_list)
        num_rows = (num_vars + 1) // 2  # Round up to ensure enough rows

        # Get unique datasets in the file
        datasets = df['dataset_name'].unique()

        # Generate color mapping for each dataset
        color_mapping = generate_color_mapping(datasets)

        # Create a resampling-aware figure with linked x-axes
        fig = FigureResampler(
            make_subplots(
                rows=num_rows, cols=2, shared_xaxes=True,
                subplot_titles=[f"{var['description']} ({var['unit']})" for var in variable_list],
                vertical_spacing=0.1, horizontal_spacing=0.08
            )
        )

        # Add traces (without data) and append data later using resampling
        for dataset_name, group in df.groupby('dataset_name'):
            color = color_mapping[dataset_name]

            for idx, var in enumerate(variable_list):
                row = (idx // 2) + 1
                col = (idx % 2) + 1

                fig.add_trace(
                    go.Scatter(
                        mode='lines',
                        name=dataset_name,
                        line=dict(color=color),
                        showlegend=idx==0,  # Show legend only for the first subplot
                        legendgroup = dataset_name,
                    ),
                    row=row, col=col
                )

                # Append data to the traces (resampling aware)
                fig.data[-1].update({'x': group['t'], 'y': group[var['name']]})

        # Update layout with title and shared x-axis range
        for idx in range(1, len(variable_list) + 1):
            row = (idx // 2) + 1
            col = (idx % 2) + 1
            if row == num_rows:  # Only update the x-axis for the last row
                fig.update_xaxes(title_text="Time (seconds)", row=row, col=col, matches='x')
            else:
                fig.update_xaxes(matches='x')

        # Update layout to include legend and global settings
        fig.update_layout(
            showlegend=True
        )

    except Exception as e:
        print(f"error plotting dataset: {e}")
        # Fallback plot in case of error
        fig = FigureResampler(
            make_subplots(
                rows=num_rows, cols=2, shared_xaxes=True,
                subplot_titles=[f"{var['description']} ({var['unit']})" for var in variable_list],
                vertical_spacing=0.04, horizontal_spacing=0.05
            )
        )
        for idx, var in enumerate(variable_list):
            row = (idx // 2) + 1
            col = (idx % 2) + 1
            fig.add_trace(
                go.Scatter(x=[0, 1, 2, 3], y=[0, 1, 2, 3], mode='lines', name="test_name", showlegend=idx==0, legendgroup = "code_name"),
                row=row, col=col
            )
        fig.update_layout(
            showlegend=True,
        )

    return fig


#TODO check how to reuse traces between calls
def main_plot(df, plots_params, year_start, year_end, x_unit='years'):
    """
    Generate a main plot with subplots for Slip, Slip Rate, Shear Stress, and State using Plotly Resampler.

    Parameters:
    df (pd.DataFrame): DataFrame containing the dataset.
    year_start (int): Start year for the time series.
    year_end (int): End year for the time series.
    x_unit (str): Time unit for the x-axis. Default is 'years'.

    Returns:
    FigureResampler: Plotly figure object with dynamic resampling enabled.
    """
    try:
        # Get unique datasets in the file
        datasets = df['dataset_name'].unique()
        # Generate color mapping for each dataset
        color_mapping = generate_color_mapping(datasets)


        # Create a resampling-aware figure with linked x-axes
        fig = FigureResampler(
            make_subplots(
                rows=2, cols=2, shared_xaxes=True,  # Ensure x-axes are shared
                subplot_titles=['Slip', 'Slip Rate', 'Shear Stress', 'State'],
                vertical_spacing=0.1, horizontal_spacing=0.08
            )
        )

        # Add traces (without data) and append data later using resampling
        for dataset_name, group in df.groupby('dataset_name'):
            color = color_mapping[dataset_name]

            fig.add_trace(
                go.Scatter(mode='lines', name=dataset_name, line=dict(color=color)),
                row=1, col=1
            )
            fig.add_trace(
                go.Scatter(mode='lines', name=dataset_name, showlegend=False, line=dict(color=color)),
                row=1, col=2
            )
            fig.add_trace(
                go.Scatter(mode='lines', name=dataset_name, showlegend=False, line=dict(color=color)),
                row=2, col=1
            )
            fig.add_trace(
                go.Scatter(mode='lines', name=dataset_name, showlegend=False, line=dict(color=color)),
                row=2, col=2
            )

            # Append data to the traces (resampling aware)
            fig.data[-4].update({'x': group[x_unit], 'y': group['slip']})
            fig.data[-3].update({'x': group[x_unit], 'y': group['slip_rate']})
            fig.data[-2].update({'x': group[x_unit], 'y': group['shear_stress']})
            fig.data[-1].update({'x': group[x_unit], 'y': group['state']})

        # Update axis titles
        fig.update_xaxes(title_text=x_unit, matches='x')  # Ensure all x-axes are linked
        fig.update_yaxes(title_text="Slip (m)", row=1, col=1)
        fig.update_yaxes(title_text="Slip rate (log10 m/s)", row=1, col=2)
        fig.update_yaxes(title_text="Shear stress (MPa)", row=2, col=1)
        fig.update_yaxes(title_text="State (log10 s)", row=2, col=2)

        # Define time ranges based on x_unit
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

        # Update layout with title and shared x-axis range
        fig.update_layout(
            showlegend=True,
            xaxis=dict(range=[time_start, time_end])  # Sync initial x-axis range
        )

    except Exception as e:
        print(f"error plotting dataset: {e}")
        # Fallback plot in case of error
        fig = FigureResampler(
            make_subplots(
                rows=2, cols=2, shared_xaxes=True,
                subplot_titles=['Slip', 'Slip Rate', 'Shear Stress', 'State'],
                vertical_spacing=0.04, horizontal_spacing=0.05
            )
        )
        for i in range(1, 3):
            for j in range(1, 3):
                fig.add_trace(
                    go.Scatter(x=[0, 1, 2, 3], y=[0, 1, 2, 3], mode='lines'),
                    row=i, col=j
                )
        fig.update_layout(
            showlegend=True,
        )

    return fig
