from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quantmind.graph.workflow import QuantMindWorkflow
from quantmind.utils.report import render_text_report


if __name__ == "__main__":
    state = QuantMindWorkflow().run("600519", "2026-06-05")
    print(render_text_report(state))
