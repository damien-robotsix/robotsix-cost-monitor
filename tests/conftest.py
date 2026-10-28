"""Root pytest configuration shared by the whole test suite."""

import faulthandler

# Dump a Python traceback to stderr if the interpreter crashes (e.g. a
# pytest-xdist worker segfault), so CI logs carry a fault trace.
# Diagnoses CI run 40632182984 (Python 3.14.8): an xdist worker died in
# test_get_config_returns_app_state_config, surfacing only as pytest-xdist's
# internal ``assert not crashitem`` with no native trace. This is the in-repo
# stand-in for PYTHONFAULTHANDLER=1, which the reusable python-ci workflow
# cannot set from this repo.
faulthandler.enable()
