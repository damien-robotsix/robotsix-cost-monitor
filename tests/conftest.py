"""Root pytest configuration shared by the whole test suite."""

import faulthandler

# Dump a Python traceback to stderr if the interpreter crashes (e.g. a
# pytest-xdist worker segfault), so CI logs carry a fault trace.
#
# Why this exists: in CI run 40632182984 (and its re-run) on Python 3.14.8,
# an xdist worker segfaulted in test_get_config_returns_app_state_config
# with no Python traceback. The only output was pytest-xdist's
# ``INTERNALERROR ... assert not crashitem``.
#
# How it works: pytest imports this root conftest in every pytest process,
# including each xdist worker. Enabling faulthandler at module level
# therefore arms it in the workers too, so a native crash dumps the Python
# stack of every thread to stderr. This is the in-repo stand-in for
# PYTHONFAULTHANDLER=1, which the reusable python-ci workflow cannot set from
# this repo.
#
# When to remove: once the worker crash is diagnosed and fixed (or the
# python-ci workflow sets PYTHONFAULTHANDLER=1 itself), this file can be
# deleted.
faulthandler.enable()
