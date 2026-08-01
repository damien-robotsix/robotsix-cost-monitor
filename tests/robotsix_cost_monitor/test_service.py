"""Unit tests for CostService.

This file has been split into per-section modules:
- test_service_edge_cases.py — edge cases (empty projects, zero hours)
- test_service_single_project.py — single project queries
- test_cache.py — cache hit / miss behaviour (TTLCache through CostService)
- test_service_cross_project.py — cross-project merging
- test_service_exception_isolation.py — exception isolation
- test_service_by_agent.py — by_agent with backend filtering
- test_service_by_agent_segmented.py — by_agent_segmented (openrouter vs subscription)
"""
