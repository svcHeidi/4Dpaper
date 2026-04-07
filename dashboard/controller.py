"""Dashboard Controller: Centralizes business logic and Quarto execution."""
from __future__ import annotations
import threading
from pathlib import Path
from typing import List, Callable, Optional
from dashboard.utils import run_quarto_render

class DashboardController:
    def __init__(self, config: dict):
        self.config = config
        self.qmd_path = Path(config["quarto_paper_path"])

    def save_file(self, file_path: str, content: str) -> bool:
        """Saves content to the specified file path."""
        try:
            Path(file_path).write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False

    def run_build(
        self,
        output_format: str = "html",
        log_callback: Optional[Callable[[str], None]] = None,
        on_finish: Optional[Callable[[int, float], None]] = None
    ):
        """Runs the Quarto build process in a background thread."""
        import time
        start_time = time.time()
        log_lines: List[str] = []

        def _target():
            try:
                exit_code = run_quarto_render(
                    self.qmd_path, 
                    log_lines, 
                    output_format=output_format if output_format != "paperview" else "html"
                )
                if output_format == "paperview":
                    # Special handling for paperview if needed, but utils.py handles it
                    exit_code = run_quarto_render(self.qmd_path, log_lines, output_format="paperview")
                
                elapsed = time.time() - start_time
                if on_finish:
                    on_finish(exit_code, elapsed)
            except Exception as e:
                log_lines.append(f"[ERROR] {e}")
                if on_finish:
                    on_finish(1, 0)

        # Start build thread
        thread = threading.Thread(target=_target, daemon=True)
        thread.start()
        
        # Monitor logs if callback provided
        if log_callback:
            def _log_monitor():
                last_len = 0
                while thread.is_alive():
                    if len(log_lines) > last_len:
                        for line in log_lines[last_len:]:
                            log_callback(line)
                        last_len = len(log_lines)
                    time.sleep(0.5)
                # Final flush
                for line in log_lines[last_len:]:
                    log_callback(line)
            
            log_thread = threading.Thread(target=_log_monitor, daemon=True)
            log_thread.start()

    def get_output_path(self, format: str = "html") -> Path:
        """Returns the expected path of the generated output file."""
        if format == "pdf":
            return self.qmd_path.parent / "_output" / "analysis_report.pdf"
        elif format == "paperview":
            return self.qmd_path.parent / "_output" / "analysis_report-paperview.html"
        return self.qmd_path.parent / "_output" / "analysis_report.html"
