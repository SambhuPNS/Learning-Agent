"""Copy the demo school (the @lakeview.example accounts) between copies of Elevate through a JSON file.

Run from backend/. Like the app, it uses data/store.json, or Firestore when FIRESTORE_ENABLED=true and
GOOGLE_CLOUD_PROJECT are set (with Application Default Credentials).

    # Load scripts/demo_data.json into this copy of Elevate
    FIRESTORE_ENABLED=true GOOGLE_CLOUD_PROJECT=your-project-id \\
      .venv/bin/python scripts/demo_data.py import --password 'choose-a-password'

    # Save this copy's demo school to scripts/demo_data.json
    FIRESTORE_ENABLED=true GOOGLE_CLOUD_PROJECT=your-project-id .venv/bin/python scripts/demo_data.py export

The file holds the accounts, profiles, student models, lessons, activity history and any topics those accounts
created. It never holds passwords or sign-in tokens: on import, the accounts that could sign in get the password
you pass. Accounts whose email already exists are left alone, so importing again is safe.
"""

import argparse
import hashlib
import json
import secrets
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import auth, student_model  # noqa: E402
from app.store import now_iso, store  # noqa: E402

DEFAULT_FILE = Path(__file__).resolve().parent / "demo_data.json"
DEFAULT_DOMAIN = "lakeview.example"
FORMAT = "elevate-demo-data"
# Credentials and internal counters are never written to the file.
PRIVATE_FIELDS = {"salt", "passwordHash", "googleId", "_learningVersion"}
# Firestore allows 500 writes per transaction; each lesson is saved with at most this many events at a time.
EVENTS_PER_WRITE = 400


def export_school(path: Path, domain: str) -> dict:
    users = sorted((user for user in store.all_users() if user.get("email", "").endswith(f"@{domain}")),
                   key=lambda user: user["email"])
    if not users:
        raise SystemExit(f"No accounts with an @{domain} email were found.")
    people = []
    for user in users:
        sessions = [session for lesson_id in sorted(user.get("progress", {}))
                    if (session := store.get_session(f"{user['id']}:{lesson_id}"))]
        events = sorted(store.recent_events(user["id"], 1_000_000), key=lambda event: (event["ts"], event["id"]))
        people.append({
            "user": {key: value for key, value in user.items() if key not in PRIVATE_FIELDS},
            "canSignIn": "passwordHash" in user,
            "model": store.get_model(user["id"], lambda: None),
            "sessions": sessions,
            "events": events,
        })
    owners = {user["id"] for user in users}
    topics = sorted((topic for topic in store.all_topics() if topic.get("createdBy") in owners), key=lambda topic: topic["id"])
    data = {"format": FORMAT, "version": 1, "exportedAt": now_iso(), "emailDomain": domain, "people": people, "topics": topics}
    # Sorted keys: Firestore does not keep map order, so this keeps re-exports of unchanged data identical.
    path.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def _restore_learning(person: dict) -> int:
    """Saves each lesson with its own activity, skipping lessons already present, so an interrupted import can be rerun."""
    user_id = person["user"]["id"]
    progress = person["user"].get("progress", {})
    model = person["model"] or student_model._new_model()
    by_lesson: dict[str | None, list[dict]] = defaultdict(list)
    for event in person["events"]:
        by_lesson[event.get("lessonId")].append(event)
    # Lessons are saved in the order they happened, so the newest activity is also the last one stored.
    sessions = sorted(person["sessions"], key=lambda session: max((e["ts"] for e in by_lesson.get(session["lessonId"], [])), default=""))
    lessons = {session["lessonId"] for session in sessions}
    # Activity that belongs to no saved lesson is kept with the last one.
    leftovers = [event for lesson_id, events in by_lesson.items() if lesson_id not in lessons for event in events]
    restored = 0
    for index, session in enumerate(sessions):
        key = f"{user_id}:{session['lessonId']}"
        if store.get_session(key):
            continue
        events = by_lesson.get(session["lessonId"], []) + (leftovers if index == len(sessions) - 1 else [])
        lesson_progress = progress.get(session["lessonId"]) or {"mastery": 0, "complete": bool(session.get("complete")), "started": True}
        for start in range(0, max(len(events), 1), EVENTS_PER_WRITE):
            _, _, _, version = store.get_learning_state(user_id, key, lambda: None)
            store.commit_learning_turn(user_id, key, version, model, session, lesson_progress, events[start:start + EVENTS_PER_WRITE])
        restored += 1
    return restored


def import_school(path: Path, password: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise SystemExit(f"{path} is not an Elevate demo data file.")

    print("Topics")
    existing = {topic["id"] for topic in store.all_topics()}
    added = [topic for topic in data.get("topics", []) if topic["id"] not in existing]
    for topic in added:
        store.save_topic(topic)
        print(f"  added {topic['title']}")
    if not added:
        print("  nothing to add")

    print("Accounts")
    created = lessons = 0
    for person in data["people"]:
        user = person["user"]
        current = store.find_user_by_email(user["email"])
        if current and current["id"] != user["id"]:
            print(f"  {user['email']} already exists as a different account, skipped")
            continue
        if not current:
            account = dict(user)
            if person["canSignIn"]:
                salt = secrets.token_bytes(16)
                account.update(salt=salt.hex(), passwordHash=auth._hash_password(password, salt))
            # The token is random and never shown, so it cannot be used to sign in; it only satisfies the storage layout.
            if not store.create_user(account, hashlib.sha256(secrets.token_bytes(32)).hexdigest()):
                print(f"  {user['email']} already exists, skipped")
                continue
            created += 1
        lessons += _restore_learning(person)
    print(f"  created {created} accounts and restored {lessons} lessons")

    print("\nSign in with (password as given):")
    for person in data["people"]:
        if person["canSignIn"]:
            print(f"  {person['user']['email']:30} {person['user'].get('role', 'student')}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="Save the demo school to a JSON file.")
    export.add_argument("--file", type=Path, default=DEFAULT_FILE)
    export.add_argument("--email-domain", default=DEFAULT_DOMAIN, help=f"Accounts to export (default @{DEFAULT_DOMAIN}).")
    load = commands.add_parser("import", help="Load the demo school from a JSON file.")
    load.add_argument("--file", type=Path, default=DEFAULT_FILE)
    load.add_argument("--password", required=True, help="Password for the accounts that can sign in (8+ characters).")
    args = parser.parse_args(argv)

    if args.command == "export":
        data = export_school(args.file, args.email_domain)
        people = data["people"]
        print(f"Saved {len(people)} accounts, {sum(len(p['sessions']) for p in people)} lessons and "
              f"{sum(len(p['events']) for p in people)} activity records to {args.file}")
        return
    if len(args.password) < 8:
        parser.error("--password must be at least 8 characters")
    import_school(args.file, args.password)


if __name__ == "__main__":
    main()
