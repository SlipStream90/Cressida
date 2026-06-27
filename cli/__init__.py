from __future__ import annotations

import argparse
import asyncio
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cressida",
        description="CRESSIDA - Autonomous Multi-Agent Software Engineering Intelligence Framework",
    )
    parser.add_argument("--version", action="version", version="0.1.0")

    subparsers = parser.add_subparsers(dest="command")

    _PROVIDER_HELP = "LLM provider: auto | anthropic | openai | gemini | groq | ollama (default: auto)"

    run_parser = subparsers.add_parser("run", help="Run a mission")
    run_parser.add_argument("brief", type=str, help="Mission brief file or inline string")
    run_parser.add_argument("--mission-id", type=str, default=None, help="Custom mission ID")
    run_parser.add_argument("--provider", type=str, default="auto", help=_PROVIDER_HELP)
    run_parser.add_argument("--ollama-model", type=str, default="llama3.2", help="Ollama model name (used when provider=ollama)")
    run_parser.add_argument("--ollama-host", type=str, default="http://localhost:11434", help="Ollama server URL")

    subparsers.add_parser("status", help="Show system status")

    feedback_parser = subparsers.add_parser("feedback", help="Submit human feedback for a task")
    feedback_parser.add_argument("task_id", type=str, help="Task ID")
    feedback_parser.add_argument("score", type=float, help="Score (0-10)")
    feedback_parser.add_argument("comment", type=str, help="Feedback comment")

    rewards_parser = subparsers.add_parser("rewards", help="Reward store operations")
    rewards_sub = rewards_parser.add_subparsers(dest="rewards_command")
    rewards_sub.add_parser("list", help="List reward records")
    rewards_export = rewards_sub.add_parser("export", help="Export reward records as JSONL")
    rewards_export.add_argument("--output", type=str, default=None, help="Output file path")

    daemon_parser = subparsers.add_parser("daemon", help="Start the autonomous CRESSIDA daemon (watcher + monitor)")
    daemon_parser.add_argument("--inbox", type=str, default="missions/inbox", help="Inbox directory to watch")
    daemon_parser.add_argument("--scheduled", type=str, default="missions/scheduled", help="Scheduled missions directory")
    daemon_parser.add_argument("--poll", type=float, default=10.0, help="Poll interval in seconds")
    daemon_parser.add_argument("--stall-threshold", type=float, default=1800.0, help="Seconds before a task is flagged stalled")
    daemon_parser.add_argument("--status-port", type=int, default=7437, help="HTTP port for status server")
    daemon_parser.add_argument("--agents-dir", type=str, default="agents", help="Path to agent spec directory")
    daemon_parser.add_argument("--root", type=str, default=".", help="Cressida root directory")
    daemon_parser.add_argument("--provider", type=str, default="auto", help=_PROVIDER_HELP)
    daemon_parser.add_argument("--ollama-model", type=str, default="llama3.2", help="Ollama model name (used when provider=ollama)")
    daemon_parser.add_argument("--ollama-host", type=str, default="http://localhost:11434", help="Ollama server URL")
    daemon_parser.add_argument("--obsidian-vault", type=str, default="", help="Path to your Obsidian vault (enables bidirectional sync)")
    daemon_parser.add_argument("--obsidian-folder", type=str, default="Cressida", help="Subfolder inside the vault for Cressida notes")

    resolve_parser = subparsers.add_parser("resolve-escalation", help="Resolve a BOND escalation to unblock a mission")
    resolve_parser.add_argument("mission_id", type=str, help="Mission ID")
    resolve_parser.add_argument("action", type=str, help="Resolution action description")

    return parser


async def async_main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        from .commands import run_mission
        return await run_mission(args)

    elif args.command == "status":
        from .commands import show_status
        return await show_status(args)

    elif args.command == "feedback":
        from .commands import submit_feedback
        return await submit_feedback(args)

    elif args.command == "rewards":
        if args.rewards_command == "list":
            from .commands import list_rewards
            return await list_rewards(args)
        elif args.rewards_command == "export":
            from .commands import export_rewards
            return await export_rewards(args)
        else:
            print("Usage: cressida rewards list|export")
            return 1

    elif args.command == "daemon":
        from .commands import start_daemon
        return await start_daemon(args)

    elif args.command == "resolve-escalation":
        from .commands import resolve_escalation
        return await resolve_escalation(args)

    else:
        parser.print_help()
        return 0


def main() -> int:
    return asyncio.run(async_main())
