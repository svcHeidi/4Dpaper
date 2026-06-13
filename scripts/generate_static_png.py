import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path


def generate_png():
    """Generates a sample PNG plot in `media/`."""
    x = np.linspace(0, 10, 100)
    y = np.sin(x)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(x, y, linewidth=2, color="darkblue")
    ax.set_title("Static Matplotlib PNG Example")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Amplitude")
    ax.grid(True, linestyle="--", alpha=0.7)

    media_dir = Path(__file__).parent.parent / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    out_path = media_dir / "static_example.png"

    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Generated static PNG at: {out_path}")

if __name__ == "__main__":
    generate_png()
