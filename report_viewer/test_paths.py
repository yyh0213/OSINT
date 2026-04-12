import os
import sys

print("Current Working Dir:", os.getcwd())
print("__file__ is:", __file__)
print("server REPORT_DIR:", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "OSINT_REPORT")))

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import analyzer
print("analyzer.__file__ is:", analyzer.__file__)
print("analyzer save_dir:", os.path.abspath(os.path.join(os.path.dirname(analyzer.__file__), "OSINT_REPORT")))
