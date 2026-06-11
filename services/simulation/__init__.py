"""
MARG Simulation Package
=======================
Railway digital twin for the NDLS–CNB corridor.

Quick start::

    from services.simulation import SimulationEngine, SimulationConfig

    config = SimulationConfig(
        sim_start_min   = 360.0,   # 06:00
        sim_end_min     = 720.0,   # 12:00
        enable_fog      = True,
        enable_blockage = True,
    )
    engine = SimulationEngine(config)
    engine.build()
    stats = engine.run()
    print(engine.metrics.to_json())
"""

from .engine import SimulationEngine, SimulationConfig

__version__ = "1.0.0"

__all__ = [
    "SimulationEngine",
    "SimulationConfig",
    "__version__",
]
