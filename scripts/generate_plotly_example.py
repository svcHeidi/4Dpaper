import json
import numpy as np
import plotly.graph_objects as go
from pathlib import Path

def generate_example():
    # 1. Create a 3D surface plot data
    x = np.linspace(-5, 5, 50)
    y = np.linspace(-5, 5, 50)
    xGrid, yGrid = np.meshgrid(y, x)
    R = np.sqrt(xGrid ** 2 + yGrid ** 2)
    z = np.sin(R)

    fig = go.Figure(data=[go.Surface(
        z=z, 
        x=x, 
        y=y,
        colorscale='Viridis',
        showscale=False
    )])

    fig.update_layout(
        scene=dict(
            xaxis_title='X Axis',
            yaxis_title='Y Axis',
            zaxis_title='Z Axis',
            camera=dict(
                eye=dict(x=1.5, y=1.5, z=1.5)
            )
        ),
        margin=dict(l=0, r=0, b=0, t=0)
    )

    # 2. Convert to JSON and save
    media_dir = Path(__file__).parent.parent / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    out_path = media_dir / "example_graph.json"
    
    # We write it out using json string representation
    with open(out_path, "w") as f:
        f.write(fig.to_json())
        
    print(f"✅ Generated Plotly JSON graph at: {out_path}")

if __name__ == "__main__":
    generate_example()
