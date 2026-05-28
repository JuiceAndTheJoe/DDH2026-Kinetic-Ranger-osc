"""Root entrypoint for OSC's Python runtime.

OSC's auto-detection looks for an ``app`` object in a top-level module
(``main.py``, ``app.py``, ...). The real FastAPI app lives in the
package; this shim just re-exports it.
"""
from kinetic_ranger.api.main import app

__all__ = ["app"]
