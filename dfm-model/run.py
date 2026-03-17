#!/usr/bin/env python3
# run.py
# Entry point. Run with:  python run.py [path/to/file.step]
# Writes a self-contained HTML report next to the input file on completion.

import logging
import os
import subprocess
import sys

from sourcing.pipeline import process_step_for_basics, to_report_dict
from sourcing.reporting.html_report import generate_report_html

logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s %(name)s: %(message)s",
)

if __name__ == "__main__":
    filepath = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "/Users/jrstauff/Desktop/Sourcing_Software/Sample_Parts/bracket1.step"
    )
    try:
        result    = process_step_for_basics(filepath)
        report    = to_report_dict(filepath, result)

        import json
        print(json.dumps(report))
        html_path = generate_report_html(report)
        logging.getLogger(__name__).info(f"Report written → {html_path}")

        # Open automatically in the default browser
        # if sys.platform == "darwin":
            # subprocess.Popen(["open", html_path])
        # elif sys.platform.startswith("linux"):
            # subprocess.Popen(["xdg-open", html_path])
        # elif sys.platform == "win32":
            # os.startfile(html_path)

    except Exception as e:
        logging.getLogger(__name__).exception(f"Error: {e}")