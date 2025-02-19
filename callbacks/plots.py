from mpl_toolkits.axes_grid1.axes_divider import make_axes_area_auto_adjustable

from callbacks.utils import generate_color_mapping
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import numpy as np


def main_time_plot_dynamic(df, variable_list):
    """
    Generate a dynamic plot with subplots based on a list of variable dictionaries.

    Parameters:
    df (pd.DataFrame): DataFrame containing the dataset.
    variable_list (list): List of dictionaries with keys 'name', 'unit', and 'description'.
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

        fig = make_subplots(
            rows=num_rows, cols=2, shared_xaxes=True,
            subplot_titles=[f"{var['description']} ({var['unit']})" for var in variable_list],
            vertical_spacing=0.1, horizontal_spacing=0.08
        )

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
                        showlegend=idx == 0,  # Show legend only for the first subplot
                        legendgroup=dataset_name,
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
        fig = make_subplots(
            rows=num_rows, cols=2, shared_xaxes=True,
            subplot_titles=[f"{var['description']} ({var['unit']})" for var in variable_list],
            vertical_spacing=0.04, horizontal_spacing=0.05
        )
        for idx, var in enumerate(variable_list):
            row = (idx // 2) + 1
            col = (idx % 2) + 1
            fig.add_trace(
                go.Scatter(x=[0, 1, 2, 3], y=[0, 1, 2, 3], mode='lines', name="test_name", showlegend=idx == 0,
                           legendgroup="code_name"),
                row=row, col=col
            )
        fig.update_layout(
            showlegend=True,
        )
    return fig


def main_surface_plot_dynamic(df, variable_dict, plot_type="3d_surface"):
    """
    Generate a dynamic plot with subplots based on a list of variable dictionaries.

    Parameters:
    df (pd.DataFrame): DataFrame containing the dataset.
    variable_dict (list): dictionaries with keys 'name', 'unit', and 'description'.
    Returns:
    Plotly figure object
    """
    try:
        # Calculate the number of rows needed for a 2-column layout
        num_ds = len(df['dataset_name'].unique())
        num_rows = (num_ds + 1) // 2  # Round up to ensure enough rows

        if num_ds == 1:
            num_cols = 1
        else:
            num_cols = 2

        # Get unique datasets in the file
        datasets = df['dataset_name'].unique()
        max_abs_value = 0.5

        fig = make_subplots(
            rows=num_rows, cols=num_cols,
            specs=[[{'type': 'surface' if plot_type == "3d_surface" else 'heatmap'} for _ in range(num_cols)] for _ in
                   range(num_rows)],
            subplot_titles=[f"Dataset: {name}" for name in datasets],
            vertical_spacing=0.1, horizontal_spacing=0.08
        )

        for i, dataset_name in enumerate(datasets):
            row = (i // num_cols) + 1
            col = (i % num_cols) + 1

            dataset_df = df[df['dataset_name'] == dataset_name]

            if plot_type == "3d_surface":
                v_disp_2d = dataset_df[variable_dict['name']].values.reshape(
                    (len(dataset_df['x'].unique()), len(dataset_df['y'].unique())))

                fig.add_trace(go.Surface(
                    x=dataset_df['x'].unique(),
                    y=dataset_df['y'].unique(),
                    z=v_disp_2d,
                    colorscale='RdBu_r',  # Reversed RdBu colormap
                    cmin=-max_abs_value,  # Center colorbar on 0
                    cmax=max_abs_value,  # Symmetric range
                    colorbar=dict(title=f"{variable_dict['name']} ({variable_dict['unit']})")
                ), row=row, col=col)

                # Update the scene for each subplot
                scene_key = f'scene{i + 1}' if i > 0 else 'scene'
                fig.update_layout({
                    scene_key: dict(
                        xaxis=dict(title='x (m)'),
                        yaxis=dict(title='y (m)'),
                        zaxis=dict(title=f"{variable_dict['name']} ({variable_dict['unit']})")
                    )
                })

            elif plot_type == "heatmap":
                fig.add_trace(go.Heatmap(
                    x=dataset_df['x'],  # x-axis grid points
                    y=dataset_df['y'],  # z-axis grid points
                    z=dataset_df[variable_dict['name']],  # Gridded v-disp values
                    zmin=-max_abs_value,  # Center colorbar on 0
                    zmax=max_abs_value,  # Symmetric range
                    zsmooth=False,
                    colorscale='RdBu_r',  # Reversed RdBu colormap
                    colorbar=dict(title=f"{variable_dict['name']} ({variable_dict['unit']})")  # Add a colorbar with a title
                ), row=row, col=col)

                # Update the axes for each subplot
                xaxis_key = f'xaxis{i + 1}' if i > 0 else 'xaxis'
                yaxis_key = f'yaxis{i + 1}' if i > 0 else 'yaxis'
                fig.update_layout({
                    xaxis_key: dict(title='x (m)'),
                    yaxis_key: dict(title='y (m)')
                })

        # Global layout updates
        if plot_type == "3d_surface":
            fig.update_layout(
                title='Surface Plot of x vs y colored by ssha (Regridded Data)',
                template='plotly_white'
            )
        elif plot_type == "heatmap":
            fig.update_layout(
                title='Heatmap of x vs y colored by SSHA (Regridded Data)',
                template='plotly_white'
            )
            fig.update_xaxes(matches='x')
            fig.update_yaxes(matches='y')


    except Exception as e:
        print(f"error plotting dataset: {e}")

        x = np.linspace(-2, 2, 5)  # 5 points along x
        y = np.linspace(-2, 2, 5)  # 5 points along y
        X, Y = np.meshgrid(x, y)
        Z = np.sin(X) * np.cos(Y)  # Sample v_disp_2d values

        # Compute the maximum absolute value in Z
        max_abs_value = np.max(np.abs(Z))

        # Create the surface plot with centered colorbar
        fig = go.Figure()
        fig.add_trace(go.Surface(
            x=x,
            y=y,
            z=Z,
            colorscale='RdBu_r',  # Reversed RdBu colormap
            cmin=-max_abs_value,  # Center colorbar on 0
            cmax=max_abs_value,  # Symmetric range
            colorbar=dict(title=f"{variable_dict['name']} ({variable_dict['unit']})")  # Optional: Add colorbar title
        ))

    return fig