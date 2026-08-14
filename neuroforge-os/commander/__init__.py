"""
NeuroForge Agent Commander
==========================
A control plane for the NeuroForge fleet plus the real-time command center
that visualises it.

    registry     what agents exist, how they launch, how work flows
    runner       launches them safely and supervises the processes
    interpreter  reconstructs structure from what agents print
    eventbus     ordered, replayable telemetry
    store        live fleet state and metrics
    graph        validated architecture IR for the map
    server       stdlib HTTP + SSE

Nothing here imports a third-party package: the commander runs anywhere the
pipeline already runs.
"""

__version__ = "1.0.0"
