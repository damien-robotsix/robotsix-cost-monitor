"""Root pytest configuration shared by the whole test suite."""

import faulthandler

# Dump a Python traceback to stderr if the interpreter crashes (e.g. a
# pytest-xdist worker segfault), so CI logs carry a fault trace.
faulthandler.enable()
