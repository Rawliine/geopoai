"""Central path resolution - NO HARDCODED PATHS (AGENT.md rule #8).

All file lookups (characters/owl.blend, scenes/, presets/, cache/, audio/,
output/presenter/) resolve relative to this file so scenes work across machines
(laptop, Verda instances). Also resolves the pinned Blender executable.

TODO: implement.
"""
