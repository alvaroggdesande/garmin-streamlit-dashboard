# conftest.py — ensure repo root is importable so `from utils import ...` works under pytest.
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
