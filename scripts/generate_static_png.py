import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

def generate_png():
    x = np.linspace(0, 10, 100)
    y = np.sin(x)

    plt.figure(figsize=(8, 4))
    plt.plot(x, y, linewidth=2, color='darkblue')
    plt.title('Static Matplotlib PNG Example')
    plt.xlabel('Time (s)')
    plt.ylabel('Amplitude')
    plt.grid(True, linestyle='--', alpha=0.7)
    
    media_dir = Path(__file__).parent.parent / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    out_path = media_dir / "static_example.png"
    
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f"✅ Generated static PNG at: {out_path}")

if __name__ == "__main__":
    generate_png()
