"""Physical module loading for direct scripts and unittest discovery.

Load a fresh instance so a custody fault patched in one suite cannot leak into
another. This helper owns no protocol, source generation or admission decisions.
"""
import importlib.util


def load_script(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
