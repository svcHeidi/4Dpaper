import os, sys, re, html, shutil
from pathlib import Path

_project_root = Path(os.getcwd())
output_dir = _project_root / "examples/niederer/_output"
if not output_dir.exists(): output_dir.mkdir(parents=True)

html_path = output_dir / "main.html"
# Fake content with placeholder
content = '<iframe data-fourd-inject="examples/niederer/state/figures/niederer-first.html"></iframe>'
with open(html_path, "w") as f:
    f.write(content)

INJECT_PATTERN = re.compile(r'data-fourd-inject="([^"]+)"')

def repl(m: re.Match) -> str:
    fig_path_rel = m.group(1)
    fig_path_abs = _project_root / fig_path_rel
    
    out_fig_path = output_dir / fig_path_rel
    out_fig_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fig_path_abs, out_fig_path)
    try:
        rel_src = os.path.relpath(out_fig_path, html_path.parent)
    except ValueError:
        rel_src = f"/{fig_path_rel}"
    return f'src="{rel_src}"'

new_content = INJECT_PATTERN.sub(repl, content)
print("INJECTED: ", new_content)
print("EXISTS:", (output_dir / "examples/niederer/state/figures/niederer-first.html").exists())
