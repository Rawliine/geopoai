"""Validate a shot JSON against schema/presenter_schema.json (CI gate).

Usage:
    python -m presenter_renderer.schema.validator <shot.json>

Uses jsonschema (already a project dependency). LLM-authored shots default to
quality=preview until human approval.

TODO: implement.
"""
