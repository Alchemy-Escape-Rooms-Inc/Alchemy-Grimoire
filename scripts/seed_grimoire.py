"""
Grimoire Seeder
===============
One-time script to import historical debug log entries and TODO items
from the Grimoire markdown files into the WatchTower SQLite database.

Run from the project root:
    python scripts/seed_grimoire.py

Safe to re-run — checks a seed flag before importing.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from models import database as db
from models.grimoire_loader import parse_todo_md, parse_debug_log_md


def is_already_seeded() -> bool:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as n FROM debug_log WHERE created_by = 'grimoire_import'"
        ).fetchone()
        return row["n"] > 0


def seed_debug_log(issues: list[dict], dry_run: bool = False) -> int:
    count = 0
    for issue in issues:
        if dry_run:
            print(f"  [DEBUG] [{issue['severity'].upper()}] {issue['title'][:80]}"
                  f"  {'✅ resolved' if issue['resolved'] else '🔴 open'}")
            count += 1
            continue

        with db.get_db() as conn:
            cursor = conn.execute(
                """INSERT INTO debug_log
                   (device_name, severity, title, description, resolution, resolved, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    issue.get("device_name"),
                    issue.get("severity", "info"),
                    issue["title"],
                    issue.get("description"),
                    issue.get("resolution"),
                    1 if issue.get("resolved") else 0,
                    "grimoire_import",
                )
            )
            count += 1

    return count


def seed_todos(todos: list[dict], dry_run: bool = False) -> int:
    count = 0
    for todo in todos:
        if dry_run:
            print(f"  [TODO] [{todo['priority'].upper()}] {todo['title'][:80]}")
            count += 1
            continue

        db.add_todo(
            title=todo["title"],
            device_name=todo.get("device_name"),
            description=todo.get("description"),
            priority=todo.get("priority", "normal"),
        )
        count += 1

    return count


def main():
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv

    print()
    print("=" * 60)
    print("  📖 Grimoire → WatchTower Seeder")
    print("=" * 60)
    print()

    db.init_db(config.DATABASE_PATH)

    if is_already_seeded() and not force:
        print("⚠️  Database already seeded. Use --force to re-seed.")
        print("   (This would create duplicate entries)")
        return

    if dry_run:
        print("🔍 DRY RUN — no changes will be written\n")

    # Parse markdown files
    print("Parsing debug-log.md...")
    issues = parse_debug_log_md()
    print(f"  Found {len(issues)} issues\n")

    print("Parsing todo.md...")
    todos = parse_todo_md()
    print(f"  Found {len(todos)} TODO items\n")

    # Seed debug log
    print("Seeding debug log:")
    debug_count = seed_debug_log(issues, dry_run=dry_run)
    print(f"  {'Would import' if dry_run else 'Imported'} {debug_count} issues\n")

    # Seed todos
    print("Seeding TODO list:")
    todo_count = seed_todos(todos, dry_run=dry_run)
    print(f"  {'Would import' if dry_run else 'Imported'} {todo_count} tasks\n")

    if not dry_run:
        print("✅ Seeding complete!")
        print(f"   Debug log: {debug_count} historical issues")
        print(f"   Tasks:     {todo_count} items (open in Debug & Tasks tab)")
    else:
        print("✅ Dry run complete. Run without --dry-run to write to DB.")
    print()


if __name__ == "__main__":
    main()
