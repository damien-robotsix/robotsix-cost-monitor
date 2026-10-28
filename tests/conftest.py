"""Root pytest configuration shared by the whole test suite."""

import faulthandler

# Enable faulthandler so that a native crash in a pytest-xdist worker (e.g.
# a segfault) dumps a Python traceback to stderr, and CI logs carry a fault
# trace instead of only pytest-xdist's internal ``assert not crashitem``.
# This is the in-repo stand-in for PYTHONFAULTHANDLER=1, which the reusable
# python-ci workflow cannot set from this repo.
#
# How it works: pytest imports this root conftest in every pytest process,
# including each xdist worker. Enabling faulthandler at module level
# therefore arms it in the workers too, so a native crash dumps the Python
# stack of every thread to stderr.
#
# When to remove: once the worker crash is diagnosed and fixed (or the
# python-ci workflow sets PYTHONFAULTHANDLER=1 itself), this file can be
# deleted.
faulthandler.enable()
