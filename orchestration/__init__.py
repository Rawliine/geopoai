"""Orchestration (W20) — the episode factory as a staged state machine.

One persistent artifact (episodes/<id>/episode.json) walks a fixed stage
sequence. Authoring ("brain") stages are satisfied by a pluggable brain (W24);
mechanical stages run inline. Stages never know which brain ran.
"""
