# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Prism CLI - main command router."""

import argparse
import os
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
    p_extract.add_argument(
        "--backend",
        choices=["claude", "cursor"],
        help="Force agent CLI backend (default: auto from config/observations)",
    )

    # review
    p_review = subparsers.add_parser("review", help="Review current session for conversational insights")
    p_review.add_argument("--session", required=True, help="Session ID to review")
    p_review.add_argument("--project", help="Override project ID")
    p_review.add_argument(
        "--backend",
        choices=["claude", "cursor"],
        help="Force agent CLI backend (default: auto from config/observations)",
    )

    # learn
    p_learn = subparsers.add_parser("learn", help="Manually teach a preference or fact")
    p_learn.add_argument("text", nargs='+', help="The knowledge to learn")
    p_learn.add_argument("--scope", choices=["project", "global"], default="project")
    p_learn.add_argument("--project", help="Override project ID")

    # forget
    p_forget = subparsers.add_parser("forget", help="Archive a knowledge entry")
    p_forget.add_argument("id", help="Entry ID to forget")

    # correct
    p_correct = subparsers.add_parser("correct", help="Supersede a knowledge entry with correction")
    p_correct.add_argument("id", help="Entry ID to correct")
    p_correct.add_argument("text", nargs='+', help="The corrected knowledge")

    # unlock
    subparsers.add_parser("unlock", help="Force-clear a stuck extraction lock")

    # disable
    p_disable = subparsers.add_parser("disable", help="Disable a Prism feature")
    p_disable.add_argument(
        "feature",
        choices=["hook"],
        help="Feature to disable. 'hook' removes capture hooks from .claude/settings.local.json "
             "and .cursor/hooks.json — stops automatic observation capture and the AI "
             "extraction/review calls it triggers. MCP, skills, and all CLI commands "
             "remain fully functional.",
    )

    # enable
    p_enable = subparsers.add_parser("enable", help="Re-enable a Prism feature")
    p_enable.add_argument(
        "feature",
        choices=["hook"],
        help="Feature to enable. 'hook' re-adds capture hooks for Claude Code and Cursor.",
    )

    # reset
    p_reset = subparsers.add_parser("reset", help="Delete all project data and start fresh")
    p_reset.add_argument("--project", help="Override project ID")
    p_reset.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    # uninstall
    p_uninstall = subparsers.add_parser(
        "uninstall",
        help="Remove Prism from this project (undoes prism init)",
    )
    p_uninstall.add_argument("--project", help="Override project ID")
    p_uninstall.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    # sync
    p_sync = subparsers.add_parser("sync", help="Regenerate .claude/prism.md from active engrams")
    p_sync.add_argument("--project", help="Override project ID")
    p_sync.add_argument("--quiet", action="store_true", help="Suppress output")

    # maintain
    p_maintain = subparsers.add_parser("maintain", help="Run confidence decay, archive expired")
    p_maintain.add_argument("--quiet", action="store_true", help="Suppress output (for hooks)")

    # promote
    p_promote = subparsers.add_parser("promote", help="Promote engram to publishable skill format")
    p_promote.add_argument("id", help="Engram ID to promote")
    p_promote.add_argument("--name", dest="skill_name", help="Override auto-generated skill name")

    # procedures
    # stats
    p_stats = subparsers.add_parser("stats", help="Show how often engrams are retrieved via MCP")
    p_stats.add_argument("--days", type=int, default=30, help="Window in days (default 30)")
    p_stats.add_argument("--limit", type=int, default=10, help="Top engrams to show (default 10)")
    p_stats.add_argument("--json", action="store_true", dest="json_output",
                         help="Output machine-readable JSON")
    p_stats.add_argument("--project", help="Override project ID")

    # log
    p_log = subparsers.add_parser("log", help="Show recent observations or extractions")
    p_log.add_argument("--last", type=int, default=20, help="Number of entries")
    p_log.add_argument("--extractions", action="store_true", help="Show extraction history")
    p_log.add_argument("--insights", action="store_true", help="Show session review insights only")
    p_log.add_argument("--rejected", action="store_true",
                       help="Show rejected candidates with failing gate reasons")
    p_log.add_argument("--json", action="store_true", dest="json_output",
                       help="Output raw JSONL")

    # analyze-sessions
    p_sessions = subparsers.add_parser("analyze-sessions",
                                       help="Analyze existing Claude Code sessions")
    p_sessions.add_argument("query", nargs="?", default=None,
                            help="Search session content via SQLite FTS5 (0 tokens). "
                                 "Combine with --last/--since/--all. Not compatible with --extract")
    p_sessions.add_argument("--all", action="store_true", dest="all_projects",
                            help="Analyze all projects (not just current)")
    p_sessions.add_argument("--extract", action="store_true",
                            help="Run extraction after analysis (ignored when query is set)")
    p_sessions.add_argument("--dry-run", action="store_true", dest="dry_run",
                            help="Show what would be analyzed without writing")
    p_sessions.add_argument("--list", action="store_true", dest="list_sessions",
                            help="List available sessions and counts")
    p_sessions.add_argument("--since", help="Only analyze sessions after DATE (YYYY-MM-DD)")
    p_sessions.add_argument("--last", type=int, help="Only analyze last N sessions")
    p_sessions.add_argument(
        "--source",
        choices=["claude", "cursor", "all"],
        default="all",
        help="Session source to analyze: claude (Claude Code), cursor (Cursor IDE), or all (default)"
    )
    p_sessions.add_argument("--project", help="Override project ID")
    p_sessions.add_argument("--force", action="store_true",
                            help="Re-analyze sessions even if already processed")

    # dashboard
    p_dashboard = subparsers.add_parser("dashboard", help="Launch the local web dashboard")
    p_dashboard.add_argument("--port", type=int, default=4318, help="Port to serve on (default 4318)")
    p_dashboard.add_argument("--no-open", action="store_true", dest="no_open",
                             help="Don't auto-open a browser")

    # config
    p_config = subparsers.add_parser("config", help="Get or set configuration")
    p_config.add_argument("key", nargs="?", help="Config key")
    p_config.add_argument("value", nargs="?", help="Config value to set")

    # registry
    registry_parser = subparsers.add_parser("registry", help="Manage skill registries")
    registry_sub = registry_parser.add_subparsers(dest="registry_command")

    # registry create
    registry_sub.add_parser("create", help="Create a new registry (guided wizard)")

    # registry add
    reg_add = registry_sub.add_parser("add", help="Add a registry")
    reg_add.add_argument("name", help="Registry name (kebab-case)")
    reg_add.add_argument("--url", required=True, help="Registry Worker URL")
    reg_add.add_argument("--token", default="", help="API token")
    reg_add.add_argument("--read-only", action="store_true", dest="read_only", help="Mark as read-only")

    # registry remove
    reg_rm = registry_sub.add_parser("remove", help="Remove a registry")
    reg_rm.add_argument("name", help="Registry name to remove")

    # registry list
    registry_sub.add_parser("list", help="Show configured registries")

    # registry default
    reg_def = registry_sub.add_parser("default", help="Set default write target")
    reg_def.add_argument("name", help="Registry name to set as default")

    # registry token
    token_parser = registry_sub.add_parser("token", help="Manage API tokens")
    token_sub = token_parser.add_subparsers(dest="token_command")

    token_create = token_sub.add_parser("create", help="Generate a new API token")
    token_create.add_argument("name", help="Registry name")

    token_revoke = token_sub.add_parser("revoke", help="Revoke an API token")
    token_revoke.add_argument("name", help="Registry name")
    token_revoke.add_argument("token_value", help="Token to revoke")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Skip version check for internal/hook-called commands to avoid noise
    if args.command not in ("sync", "maintain", "review", "unlock"):
        try:
            from .version_check import maybe_print_update_notice
            maybe_print_update_notice()
        except Exception:
            pass

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
        results = run_extraction(project_id, backend=getattr(args, "backend", None))
        print("\nResults: {} extracted, {} approved, {} rejected, {} modified".format(
            results['extracted'], results['approved'],
            results['rejected'], results['modified']))
        # Ensure sync happened (EXT-05 belt-and-suspenders)
        if results['approved'] > 0 or results['modified'] > 0:
            try:
                from .sync import sync_claude_code
                sync_claude_code(project_id)
            except Exception:
                pass

    elif args.command == "review":
        from .review import run_review
        from .project import detect_project_id
        project_id = args.project or detect_project_id()
        results = run_review(args.session, project_id, backend=getattr(args, "backend", None))
        if results.get("insights", 0) > 0:
            print("Review complete: {} insights captured".format(results['insights']))
        else:
            print("Review complete: no new insights (status: {})".format(
                results.get('status', 'unknown')))

    elif args.command == "learn":
        from .commands import cmd_learn
        cmd_learn(" ".join(args.text), project_id=args.project, scope=args.scope)

    elif args.command == "forget":
        from .commands import cmd_forget
        cmd_forget(args.id)

    elif args.command == "correct":
        from .commands import cmd_correct
        cmd_correct(args.id, " ".join(args.text))

    elif args.command == "unlock":
        from .commands import cmd_unlock
        cmd_unlock()

    elif args.command == "disable":
        from .commands import cmd_disable_hook
        cmd_disable_hook()

    elif args.command == "enable":
        from .commands import cmd_enable_hook
        cmd_enable_hook()

    elif args.command == "reset":
        from .commands import cmd_reset
        cmd_reset(project_id=args.project, yes=args.yes)

    elif args.command == "uninstall":
        from .commands import cmd_uninstall
        cmd_uninstall(project_id=args.project, yes=args.yes)

    elif args.command == "sync":
        from .sync import sync_claude_code
        from .project import detect_project_id
        project_id = args.project or detect_project_id()
        sync_claude_code(project_id)
        if not getattr(args, "quiet", False):
            print(f"Synced context for project {project_id}")

    elif args.command == "maintain":
        from .commands import cmd_maintain
        cmd_maintain(quiet=getattr(args, "quiet", False))

    elif args.command == "promote":
        from .bridge import cmd_promote
        cmd_promote(args.id, name_override=args.skill_name)

    elif args.command == "stats":
        from .commands import cmd_stats
        cmd_stats(project_id=args.project, days=args.days,
                  json_output=args.json_output, limit=args.limit)

    elif args.command == "log":
        from .commands import cmd_log
        cmd_log(last_n=args.last, extractions=args.extractions,
                insights=args.insights, rejected=args.rejected,
                json_output=args.json_output)

    elif args.command == "analyze-sessions":
        _cmd_analyze_sessions(args)

    elif args.command == "dashboard":
        from .dashboard import serve_dashboard
        serve_dashboard(port=args.port, no_open=args.no_open)

    elif args.command == "config":
        from .commands import cmd_config
        cmd_config(args.key, args.value)

    elif args.command == "registry":
        from .commands import cmd_registry
        cmd_registry(args)

    else:
        parser.print_help()

    # Safety net: check if auto-extraction should trigger
    # Skip for commands that already handle extraction or are too early
    if args.command not in ("init", "extract", "review", "config", "analyze-sessions", "sync", "disable", "enable", "uninstall", "stats", None):
        try:
            from .project import detect_project_id
            from .trigger import maybe_trigger_extraction
            project_id = getattr(args, "project", None) or detect_project_id()
            maybe_trigger_extraction(project_id, quiet=False)
        except Exception:
            pass  # Never let the safety net break a command


def _cmd_query_sessions(args, project_id: str) -> None:
    """Search observations via SQLite FTS5."""
    from datetime import datetime
    from .search import search_sessions

    ts_from = None
    if args.since:
        try:
            ts_from = int(datetime.strptime(args.since, "%Y-%m-%d").timestamp())
        except ValueError:
            print(f"Invalid --since date: {args.since!r}. Expected YYYY-MM-DD.")
            return

    limit = args.last if args.last else 10
    scope_parts = []
    if args.since:
        scope_parts.append(f"since {args.since}")
    if args.last:
        scope_parts.append(f"limit {args.last}")
    scope = f" ({', '.join(scope_parts)})" if scope_parts else ""
    print(f"Searching observations{scope} for: {args.query!r}\n")

    results = search_sessions(
        args.query,
        project_id=None if args.all_projects else project_id,
        limit=limit,
        ts_from=ts_from,
    )

    if not results:
        print("No matches found.")
        return

    for i, r in enumerate(results, 1):
        ts_str = datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d %H:%M")
        print(f"{i}. obs:{r['id']}  session:{r['session_id'][:12]}  {ts_str}")
        print(f"   {r['snippet']}\n")


def _cmd_analyze_sessions(args) -> None:
    """Analyze existing Claude Code session transcripts."""
    from .sessions import analyze_all_sessions, list_all_sessions, list_cursor_sessions, list_sessions

    project_id = args.project
    if not project_id and not args.all_projects:
        from .project import detect_project_id
        project_id = detect_project_id()

    if args.query:
        _cmd_query_sessions(args, project_id)
        return

    if args.list_sessions:
        list_func = {
            "claude": list_sessions,
            "cursor": list_cursor_sessions,
            "all": list_all_sessions,
        }.get(args.source, list_all_sessions)
        sessions = list_func(
            project_filter=None if args.all_projects else project_id,
            since_date=args.since,
            last_n=args.last,
        )
        if not sessions:
            print("No sessions found.")
            return
        # Group by project
        by_project = {}
        for s in sessions:
            by_project.setdefault(s["project_id"], []).append(s)
        for pid, sess_list in sorted(by_project.items()):
            cwd = sess_list[0].get("cwd") or ""
            name = os.path.basename(cwd.rstrip("/")) if cwd else pid
            total_size = sum(s["size"] for s in sess_list)
            print("{} ({}): {} sessions, {:.0f} KB".format(name, pid, len(sess_list), total_size / 1024))
            import time as _time
            for s in sorted(sess_list, key=lambda x: os.path.getmtime(x["path"]) if os.path.exists(x["path"]) else 0, reverse=True):
                try:
                    date_str = _time.strftime("%Y-%m-%d", _time.localtime(os.path.getmtime(s["path"])))
                except OSError:
                    date_str = "unknown"
                print("  {}  {}  {:.0f} KB".format(s["session_id"], date_str, s["size"] / 1024))
        return

    mode = "Dry run" if args.dry_run else "Analyzing"
    scope = "all projects" if args.all_projects else "project {}".format(project_id)
    print("{}: {}\n".format(mode, scope))

    results = analyze_all_sessions(
        project_filter=project_id,
        all_projects=args.all_projects,
        dry_run=args.dry_run,
        since_date=args.since,
        last_n=args.last,
        force=getattr(args, "force", False),
        source=args.source,
    )

    print("\nSummary:")
    print("  Sessions: {} processed, {} skipped".format(results['processed'], results['skipped']))
    print("  Observations: {} total".format(results['total_observations']))
    for pid, info in results["by_project"].items():
        print("    {} ({}): {} sessions, {} observations".format(
            info['name'], pid, info['sessions'], info['observations']))

    if not args.dry_run and results["total_observations"] > 0:
        if args.extract:
            print("\nRunning extraction...")
            from .extract import run_extraction
            for pid in results["by_project"]:
                extract_results = run_extraction(pid)
                print("  {}: {} extracted, {} approved, {} rejected".format(
                    pid, extract_results['extracted'],
                    extract_results['approved'], extract_results['rejected']))
        else:
            print("\nRun 'prism extract' to process these into knowledge entries.")


if __name__ == "__main__":
    main()
