"""Prism CLI - main command router."""

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="prism",
        description="Prism - knowledge layer for Claude Code",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    subparsers.add_parser("init", help="Initialize prism for current project")

    # status
    p_status = subparsers.add_parser("status", help="Show active knowledge and project info")
    p_status.add_argument("--project", help="Override project ID")

    # extract
    p_extract = subparsers.add_parser("extract", help="Run extraction on observations")
    p_extract.add_argument("--project", help="Override project ID")

    # review
    p_review = subparsers.add_parser("review", help="Review current session for conversational insights")
    p_review.add_argument("--session", required=True, help="Session ID to review")
    p_review.add_argument("--project", help="Override project ID")

    # sync
    p_sync = subparsers.add_parser("sync", help="Generate IDE context files")
    p_sync.add_argument("--claude", action="store_true", help="Generate .claude/prism.md")
    p_sync.add_argument("--project", help="Override project ID")
    p_sync.add_argument("--output-dir", help="Override output directory")

    # learn
    p_learn = subparsers.add_parser("learn", help="Manually teach a preference or fact")
    p_learn.add_argument("text", help="The knowledge to learn")
    p_learn.add_argument("--scope", choices=["project", "global"], default="project")
    p_learn.add_argument("--project", help="Override project ID")

    # forget
    p_forget = subparsers.add_parser("forget", help="Archive a knowledge entry")
    p_forget.add_argument("id", help="Entry ID to forget")

    # correct
    p_correct = subparsers.add_parser("correct", help="Supersede a knowledge entry with correction")
    p_correct.add_argument("id", help="Entry ID to correct")
    p_correct.add_argument("text", help="The corrected knowledge")

    # maintain
    subparsers.add_parser("maintain", help="Run confidence decay, archive expired")

    # procedures
    p_procs = subparsers.add_parser("procedures", help="List procedures with stats")
    p_procs.add_argument("--project", help="Override project ID")

    # log
    p_log = subparsers.add_parser("log", help="Show recent observations or extractions")
    p_log.add_argument("--last", type=int, default=20, help="Number of entries")
    p_log.add_argument("--extractions", action="store_true", help="Show extraction history")
    p_log.add_argument("--insights", action="store_true", help="Show session review insights only")

    # analyze-sessions
    p_sessions = subparsers.add_parser("analyze-sessions",
                                       help="Analyze existing Claude Code sessions")
    p_sessions.add_argument("--all", action="store_true", dest="all_projects",
                            help="Analyze all projects (not just current)")
    p_sessions.add_argument("--extract", action="store_true",
                            help="Run extraction after analysis")
    p_sessions.add_argument("--dry-run", action="store_true", dest="dry_run",
                            help="Show what would be analyzed without writing")
    p_sessions.add_argument("--list", action="store_true", dest="list_sessions",
                            help="List available sessions and counts")
    p_sessions.add_argument("--project", help="Override project ID")

    # config
    p_config = subparsers.add_parser("config", help="Get or set configuration")
    p_config.add_argument("key", nargs="?", help="Config key")
    p_config.add_argument("value", nargs="?", help="Config value to set")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Route to handlers
    if args.command == "init":
        from .commands import cmd_init
        cmd_init()

    elif args.command == "status":
        from .commands import cmd_status
        cmd_status(project_id=args.project)

    elif args.command == "extract":
        from .extract import run_extraction
        from .project import detect_project_id
        project_id = args.project or detect_project_id()
        results = run_extraction(project_id)
        print(f"\nResults: {results['extracted']} extracted, "
              f"{results['approved']} approved, "
              f"{results['rejected']} rejected, "
              f"{results['modified']} modified")

    elif args.command == "review":
        from .review import run_review
        from .project import detect_project_id
        project_id = args.project or detect_project_id()
        results = run_review(args.session, project_id)
        if results.get("insights", 0) > 0:
            print(f"Review complete: {results['insights']} insights captured")
        else:
            print(f"Review complete: no new insights (status: {results.get('status', 'unknown')})")

    elif args.command == "sync":
        from .project import detect_project_id
        from .sync import sync_claude_code
        project_id = args.project or detect_project_id()
        sync_claude_code(project_id, output_dir=args.output_dir)

    elif args.command == "learn":
        from .commands import cmd_learn
        cmd_learn(args.text, project_id=args.project, scope=args.scope)

    elif args.command == "forget":
        from .commands import cmd_forget
        cmd_forget(args.id)

    elif args.command == "correct":
        from .commands import cmd_correct
        cmd_correct(args.id, args.text)

    elif args.command == "maintain":
        from .commands import cmd_maintain
        cmd_maintain()

    elif args.command == "procedures":
        from .commands import cmd_procedures
        cmd_procedures(project_id=args.project)

    elif args.command == "log":
        from .commands import cmd_log
        cmd_log(last_n=args.last, extractions=args.extractions, insights=args.insights)

    elif args.command == "analyze-sessions":
        _cmd_analyze_sessions(args)

    elif args.command == "config":
        _cmd_config(args.key, args.value)

    else:
        parser.print_help()

    # Safety net: check if auto-extraction should trigger
    # Skip for commands that already handle extraction or are too early
    if args.command not in ("init", "extract", "review", "config", "analyze-sessions", None):
        try:
            from .project import detect_project_id
            from .trigger import maybe_trigger_extraction
            project_id = getattr(args, "project", None) or detect_project_id()
            maybe_trigger_extraction(project_id, quiet=False)
        except Exception:
            pass  # Never let the safety net break a command


def _cmd_analyze_sessions(args) -> None:
    """Analyze existing Claude Code session transcripts."""
    from .sessions import list_sessions, analyze_all_sessions

    project_id = args.project
    if not project_id and not args.all_projects:
        from .project import detect_project_id
        project_id = detect_project_id()

    if args.list_sessions:
        sessions = list_sessions(project_filter=None if args.all_projects else project_id)
        if not sessions:
            print("No sessions found.")
            return
        # Group by project
        by_project: dict[str, list] = {}
        for s in sessions:
            by_project.setdefault(s["project_id"], []).append(s)
        for pid, sess_list in sorted(by_project.items()):
            name = __import__("os").path.basename(sess_list[0]["cwd"].rstrip("/")) if sess_list[0]["cwd"] else pid
            total_size = sum(s["size"] for s in sess_list)
            print(f"{name} ({pid}): {len(sess_list)} sessions, {total_size / 1024:.0f} KB")
        return

    mode = "Dry run" if args.dry_run else "Analyzing"
    scope = "all projects" if args.all_projects else f"project {project_id}"
    print(f"{mode}: {scope}\n")

    results = analyze_all_sessions(
        project_filter=project_id,
        all_projects=args.all_projects,
        dry_run=args.dry_run,
    )

    print(f"\nSummary:")
    print(f"  Sessions: {results['processed']} processed, {results['skipped']} skipped")
    print(f"  Observations: {results['total_observations']} total")
    for pid, info in results["by_project"].items():
        obs_path = f"~/.prism/projects/{pid}/observations.jsonl"
        print(f"    {info['name']} ({pid}): {info['sessions']} sessions, "
              f"{info['observations']} observations")

    if not args.dry_run and results["total_observations"] > 0:
        if args.extract:
            print("\nRunning extraction...")
            from .extract import run_extraction
            for pid in results["by_project"]:
                extract_results = run_extraction(pid)
                print(f"  {pid}: {extract_results['extracted']} extracted, "
                      f"{extract_results['approved']} approved, "
                      f"{extract_results['rejected']} rejected")
        else:
            print("\nRun 'prism extract' to process these into knowledge entries.")


def _cmd_config(key: "str | None", value: "str | None") -> None:
    """Get or set configuration values."""
    from .config import get_config, save_config

    config = get_config()

    if key is None:
        # Show all config
        import json
        print(json.dumps(config, indent=2))
        return

    if value is None:
        # Get single key
        if key in config:
            print(f"{key}: {config[key]}")
        else:
            print(f"Unknown config key: {key}")
        return

    # Set value (try to parse as number/bool)
    if value.lower() in ("true", "false"):
        config[key] = value.lower() == "true"
    else:
        try:
            config[key] = float(value)
            if config[key] == int(config[key]):
                config[key] = int(config[key])
        except ValueError:
            config[key] = value

    save_config(config)
    print(f"Set {key} = {config[key]}")


if __name__ == "__main__":
    main()
