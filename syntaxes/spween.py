"""Physical pinned Spween parsing adapter; execution belongs to source objects."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('spween_parser_adapter', ROOT / 'scene/parser.py')
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)
UPSTREAM = parser.UPSTREAM
BRIDGE = parser.BRIDGE
parse = parser.parse
source_shape = parser.source_shape
