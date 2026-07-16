import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASH_DIR = os.path.dirname(_HERE)
if _DASH_DIR not in sys.path:
    sys.path.insert(0, _DASH_DIR)
