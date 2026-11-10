"""Service layer: cross-project cost aggregation with a small TTL cache.

The implementation lives in :mod:`robotsix_cost_monitor.service.core`; this
package re-exports its public names so ``from robotsix_cost_monitor.service
import CostService`` keeps working.
"""

from .core import DASHBOARD_WINDOW_PRESETS, CostService

__all__ = ["DASHBOARD_WINDOW_PRESETS", "CostService"]
