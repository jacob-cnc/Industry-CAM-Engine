"""Cutting tools: tool data, the LinuxCNC tool table, insert geometry.

- tool_card_data: ToolCardData (the tool editor's record) and ToolDef conversion
- tool_table_io: .tbl serializer (canonical, machine units, wear metadata)
- filter_cascade: tool type -> allowed orientations / inserts
- insert_geometry_lookup: insert code -> front/back cutting-edge angles

Imports from: models/ only. No kernel, no Qt.

Import submodules directly (e.g. `from tools.<module> import X`); this
package re-exports nothing, so importing one light module never loads the rest.
"""
