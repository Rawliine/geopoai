"""Load a scene .blend, link the owl, and apply prop textures (Phase 2/3).

- Opens scenes/<name>.blend (selected by shot JSON `scene`)
- Confirms the owl is linked (File > Link, never appended; rule #6)
- Applies optional `map_texture`: drops a Mapbox-rendered PNG onto a named
  object (e.g. diner_table_map_plane) - cross-engine reuse (rule #7)

TODO: implement.
"""
