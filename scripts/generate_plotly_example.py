from pathlib import Path

import numpy as np
import plotly.graph_objects as go

def generate_example():
    """Generates a sample Plotly JSON figure in `media/`."""
    x = np.linspace(-5, 5, 50)
    y = np.linspace(-5, 5, 50)
    x_grid, y_grid = np.meshgrid(y, x)
    radius = np.sqrt(x_grid ** 2 + y_grid ** 2)
    z = np.sin(radius)

    fig = go.Figure(
        data=[
            go.Surface(
                z=z,
                x=x,
                y=y,
                colorscale="Viridis",
                showscale=False,
            )
        ]
    )

    fig.update_layout(
        scene=dict(
            xaxis_title="X Axis",
            yaxis_title="Y Axis",
            zaxis_title="Z Axis",
            camera=dict(eye=dict(x=1.5, y=1.5, z=1.5)),
        ),
        margin=dict(l=0, r=0, b=0, t=0),
    )

    media_dir = Path(__file__).parent.parent / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    out_path = media_dir / "example_graph.json"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(fig.to_json())

    print(f"Generated Plotly JSON graph at: {out_path}")

if __name__ == "__main__":
    generate_example()
