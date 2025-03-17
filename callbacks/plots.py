from mpl_toolkits.axes_grid1.axes_divider import make_axes_area_auto_adjustable

from callbacks.utils import generate_color_mapping
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import numpy as np


def main_time_plot_dynamic(df, variable_list, x_axis=dict({'name':'t', 'unit':'s', 'description':'Time'})):
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
        filtered_list = [item for item in variable_list if item['name'] != x_axis['name']]
        print(f"x_axis variable name: {x_axis['name']}")
        print(f"Filtered list: {filtered_list}")
        num_vars = len(filtered_list)
        num_rows = (num_vars + 1) // 2  # Round up to ensure enough rows
        print(f"Number of variables: {num_vars}, number of rows: {num_rows}")
        # Get unique datasets in the file
        datasets = df['dataset_name'].unique()

        # Generate color mapping for each dataset
        color_mapping = generate_color_mapping(datasets)

        fig = make_subplots(
            rows=num_rows, cols=2, shared_xaxes=True,
            subplot_titles=[f"{var['description']} ({var['unit']})" for var in filtered_list],
            vertical_spacing=0.1, horizontal_spacing=0.08
        )

        for dataset_name, group in df.groupby('dataset_name'):
            color = color_mapping[dataset_name]

            for idx, var in enumerate(filtered_list):
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

                # Append data to the traces
                fig.data[-1].update({'x': group[x_axis['name']], 'y': group[var['name']]})

        # Update layout with title and shared x-axis range
        for idx in range(0, len(variable_list) + 1):
            row = (idx // 2) + 1
            col = (idx % 2) + 1
            fig.update_xaxes(title_text=f"{x_axis['description']} ({x_axis['unit']})", row=row, col=col, showticklabels=True, matches='x')
            # if row == num_rows:  # Only update the x-axis for the last row
            #     fig.update_xaxes(title_text="Time (seconds)", row=row, col=col, matches='x')
            # else:
            #     fig.update_xaxes(matches='x')

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
    dynamic_height = f'{min(85 + (num_rows - 2) * 20, 150)}vh'  # Scale with num_rows
    return fig, {'width': '100%', 'height': dynamic_height}


def main_surface_plot_dynamic_v2(df, old_fig, variable_dict, plot_type="3d_surface", slider=0, slider_only=False):
    """
    Generate a dynamic plot with subplots based on a list of variable dictionaries.

    Parameters:
    df (pd.DataFrame): DataFrame containing the dataset.
    old_fig (go.Figure): Previous figure state (for partial updates).
    variable_dict (dict): Dictionary with keys 'name', 'unit', and 'description'.
    plot_type (str): Type of plot ("3d_surface" or "heatmap").
    slider (int): Current slider position (index for cross-section).
    slider_only (bool): If True, only update the cross-section, otherwise regenerate the figure.

    Returns:
    go.Figure: Plotly figure object.
    """
    try:
        datasets = df['dataset_name'].unique()
        num_ds = len(datasets)
        num_rows = num_ds//2 + num_ds % 2
        num_cols = 1 if num_ds == 1 else 2
        max_abs_value = 0.5

        print(f"num_ds: {num_ds}, num_rows: {num_rows}, num_cols: {num_cols}, slider: {slider}")

        fig = make_subplots(
            rows=num_rows,
            cols=num_cols,
            specs=[[{'type': 'surface' if plot_type == "3d_surface" else 'heatmap'}] * num_cols] if num_ds == 1 else [
                [{'type': 'surface' if plot_type == "3d_surface" else 'heatmap'} for _ in range(num_cols)]
                for _ in range(num_rows)
            ],
            subplot_titles=[f"Dataset: {name}" for name in datasets],
            vertical_spacing=0.1,
            horizontal_spacing=0.08,
        )

        for i, dataset_name in enumerate(datasets):
            print(f"Plotting dataset: {dataset_name}")
            row = (i // num_cols) + 1
            col = (i % num_cols) + 1
            dataset_df = df[df['dataset_name'] == dataset_name]
            slider_idx = dataset_df.loc[(df['y'] - slider).abs().idxmin(), 'y']

            x_unique = dataset_df['x'].unique()
            y_unique = dataset_df['y'].unique()
            v_disp_2d = dataset_df[variable_dict['name']].values.reshape((len(x_unique), len(y_unique)))
            if plot_type == "3d_surface":
                fig.add_trace(go.Surface(
                    x=x_unique,
                    y=y_unique,
                    z=v_disp_2d,
                    colorscale='RdBu_r',
                    cmin=-max_abs_value,
                    cmax=max_abs_value,
                    colorbar=dict(title=f"{variable_dict['name']} ({variable_dict['unit']})")
                ), row=row, col=col)

                scene_key = f'scene{i + 1}' if i > 0 else 'scene'
                #
                # # Add black cross-section line in the 3D scene
                y_index = np.abs(y_unique - slider_idx).argmin()
                fig.add_trace(go.Scatter3d(
                    x=x_unique,
                    y=[y_unique[y_index]] * len(x_unique),
                    z=dataset_df[dataset_df['y'] == slider_idx][variable_dict['name']],
                    mode='lines',
                    line=dict(color='black', width=3),
                    showlegend=False,
                    scene=scene_key  # Assign to correct 3D scene
                ), row=row, col=col)

                fig.update_layout({
                    scene_key: dict(
                        xaxis=dict(title='x (m)'),
                        yaxis=dict(title='y (m)'),
                        zaxis=dict(title=f"{variable_dict['name']} ({variable_dict['unit']})")
                    )
                })

            elif plot_type == "heatmap":
                fig.add_trace(go.Heatmap(
                    x=x_unique,
                    y=y_unique,
                    z=v_disp_2d,
                    zmin=-max_abs_value,
                    zmax=max_abs_value,
                    colorscale='RdBu_r',
                    colorbar=dict(title=f"{variable_dict['name']} ({variable_dict['unit']})")
                ), row=row, col=col)

                # Add the black line indicating the cross-section
                fig.add_trace(go.Scatter(
                    x=[x_unique.min(), x_unique.max()],
                    y=[slider_idx, slider_idx],
                    mode='lines',
                    line=dict(color='black', width=1),
                    showlegend=False
                ), row=row, col=col)

                xaxis_key = f'xaxis{i + 1}' if i > 0 else 'xaxis'
                yaxis_key = f'yaxis{i + 1}' if i > 0 else 'yaxis'
                fig.update_layout({
                    xaxis_key: dict(title='x (m)', scaleanchor=f"y{i + 1}" if i > 0 else "y"),
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
        num_rows = 1
        print(f"Error plotting dataset: {e}")

        x = np.linspace(-2, 2, 5)
        y = np.linspace(-2, 2, 5)
        X, Y = np.meshgrid(x, y)
        Z = np.sin(X) * np.cos(Y)

        max_abs_value = np.max(np.abs(Z))

        fig = go.Figure()
        fig.add_trace(go.Surface(
            x=x,
            y=y,
            z=Z,
            colorscale='RdBu_r',
            cmin=-max_abs_value,
            cmax=max_abs_value,
            colorbar=dict(title=f"{variable_dict['name']} ({variable_dict['unit']})")
        ))

    dynamic_height = f'{min(85 + (num_rows - 2) * 20, 150)}vh'  # Scale with num_rows
    return fig, {'width': '100%', 'height': dynamic_height}


def cross_section_plots(df, variable_dict, slider=0):
    try:
        df_cross = df[df['y'] == slider]  # Filter data for the selected cross-section
        fig = go.Figure()

        # Add traces for each dataset_name
        for dataset in df_cross['dataset_name'].unique():
            dataset_df = df_cross[df_cross['dataset_name'] == dataset]  # Filter data for this dataset

            fig.add_trace(go.Scattergl(
                x=dataset_df['x'],
                y=dataset_df[variable_dict['name']],  # Select dynamically between var1, var2, var3
                mode='lines',  # Line plot with markers
                name=dataset,  # Legend entry
                line=dict(width=2)  # Line width
            ))

        # Customize layout
        fig.update_layout(
            title=f"Cross section of {variable_dict['name']} at y={slider}",
            xaxis_title=f"x (m)",
            yaxis_title=f"{variable_dict['name']} ({variable_dict['unit']})",
            legend_title="Dataset Name",
            template="plotly_white"
        )

        # Show plot
        return fig
    except Exception as e:
        print(f"error plotting dataset: {e}")
        # Fallback plot in case of error
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(x=[0, 1, 2, 3], y=[0, 1, 2, 3], mode='lines', name="test_name", showlegend=True,
                          legendgroup="code_name"),
            )
    return fig
