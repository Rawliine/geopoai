#!/usr/bin/env python3
"""Episode orchestrator CLI — drive the W20 state machine.

  orchestrate.py new <show> <episode_id> [--format ...] [--brain ...] [--inputs f.json]
  orchestrate.py status <episode_id>
  orchestrate.py next <episode_id> [--brain ...]
  orchestrate.py validate <stage> <episode_id>
  orchestrate.py run <stage> <episode_id> [--brain ...]
  orchestrate.py qc <episode_id>
  orchestrate.py invalidate <stage|clip_id> <episode_id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from orchestration import bible as bible_mod  # noqa: E402
from orchestration import manifest as M  # noqa: E402
from orchestration import runner  # noqa: E402


def _cmd_new(args: argparse.Namespace) -> int:
    bible = bible_mod.load(args.show)
    formats = args.format or bible_mod.default_formats(bible)
    brain = args.brain or bible_mod.default_brain(bible)
    manifest = M.new_manifest(
        args.show, args.episode_id, formats, brain,
        caption_policy=bible_mod.default_caption_policy(bible),
    )
    if args.inputs:
        manifest["inputs"] = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
    ep_dir = M.episode_dir(_ROOT, args.episode_id)
    if M.manifest_path(ep_dir).exists():
        print(f"episode {args.episode_id!r} already exists at {ep_dir}", file=sys.stderr)
        return 1
    M.save(ep_dir, manifest)
    print(f"created {M.manifest_path(ep_dir)} (brain={brain}, formats={formats})")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    _, manifest = runner._load(_ROOT, args.episode_id)
    print(f"episode {manifest['episode_id']} (show {manifest['show_id']}, brain {manifest['brain']})")
    for stage in M.STAGE_SEQUENCE:
        st = manifest.get("stages", {}).get(stage, {})
        print(f"  {stage:11s} {st.get('status', 'pending')}")
    nxt = M.first_unfinished(manifest)
    print(f"next: {nxt or '(complete)'}")
    return 0


def _cmd_next(args: argparse.Namespace) -> int:
    stage, status = runner.next_stage(
        args.episode_id, repo_root=_ROOT, brain_override=args.brain
    )
    if stage is None:
        print("episode complete.")
        return 0
    print(f"{stage}: {status}")
    if status == "awaiting_brain":
        sd = M.stage_dir(M.episode_dir(_ROOT, args.episode_id), stage)
        print(f"  author {sd / 'artifact.json'} per {sd / 'instruction.md'}, then re-run.")
        return 3
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    status = runner.run_named(
        args.episode_id, args.stage, repo_root=_ROOT, brain_override=args.brain
    )
    print(f"{args.stage}: {status}")
    return 3 if status == "awaiting_brain" else 0


def _cmd_validate(args: argparse.Namespace) -> int:
    # Validation = run the (idempotent) pickup path for the stage.
    status = runner.run_named(args.episode_id, args.stage, repo_root=_ROOT)
    print(f"{args.stage}: {status}")
    return 0 if status == "done" else 3


def _cmd_qc(args: argparse.Namespace) -> int:
    try:
        status = runner.run_named(args.episode_id, "qc", repo_root=_ROOT)
    except RuntimeError as exc:
        print(f"qc: failed — {exc}")
        return 1
    print(f"qc: {status}")
    return 0


def _cmd_invalidate(args: argparse.Namespace) -> int:
    flipped = runner.invalidate(args.episode_id, args.target, repo_root=_ROOT)
    print(f"invalidated {args.target!r} → re-do: {', '.join(flipped)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Episode orchestrator (W20).")
    sub = p.add_subparsers(dest="cmd", required=True)

    pn = sub.add_parser("new", help="Create a new episode manifest.")
    pn.add_argument("show")
    pn.add_argument("episode_id")
    pn.add_argument("--format", nargs="+", choices=["horizontal", "vertical"])
    pn.add_argument("--brain", choices=["halt", "claude-cli", "gemini-cli", "api"])
    pn.add_argument("--inputs", help="JSON file with the inputs[] array.")
    pn.set_defaults(func=_cmd_new)

    ps = sub.add_parser("status", help="Show stage statuses.")
    ps.add_argument("episode_id")
    ps.set_defaults(func=_cmd_status)

    px = sub.add_parser("next", help="Run the next unfinished stage.")
    px.add_argument("episode_id")
    px.add_argument("--brain", help="Override the episode brain for this run.")
    px.set_defaults(func=_cmd_next)

    pv = sub.add_parser("validate", help="Validate/pick up a stage's authored artifact.")
    pv.add_argument("stage")
    pv.add_argument("episode_id")
    pv.set_defaults(func=_cmd_validate)

    pr = sub.add_parser("run", help="Run one named stage.")
    pr.add_argument("stage")
    pr.add_argument("episode_id")
    pr.add_argument("--brain", help="Override the episode brain for this run.")
    pr.set_defaults(func=_cmd_run)

    pq = sub.add_parser("qc", help="Run the QC stage.")
    pq.add_argument("episode_id")
    pq.set_defaults(func=_cmd_qc)

    pi = sub.add_parser("invalidate", help="Mark a stage or clip dirty for re-run.")
    pi.add_argument("target", help="A stage name or a clip id.")
    pi.add_argument("episode_id")
    pi.set_defaults(func=_cmd_invalidate)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
