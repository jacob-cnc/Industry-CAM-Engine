"""Validation module — Shapely-based runtime safety checking.

The ONLY module that imports Shapely.
Imports from: models/, geometry/

Import submodules directly (e.g. `from validation.<module> import X`); this
package re-exports nothing, so importing one light module never loads the rest.
"""
