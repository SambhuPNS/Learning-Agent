"""Copy a local store.json into the Firestore collections used by the application."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from google.cloud import firestore


def document_batches(documents: list[tuple[str, str, dict[str, Any]]], size: int = 450):
    for index in range(0, len(documents), size):
        yield documents[index:index + size]


def load_documents(data: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    documents: list[tuple[str, str, dict[str, Any]]] = []
    for collection in ("users", "tokens", "sessions", "studentModels", "topics"):
        for document_id, value in data.get(collection, {}).items():
            documents.append((collection, document_id, value))
    for user_id, user in data.get("users", {}).items():
        email = user.get("email", "").strip().lower()
        if email:
            documents.append(("userEmails", hashlib.sha256(email.encode()).hexdigest(), {"userId": user_id}))
    for event in data.get("events", []):
        if "id" not in event:
            raise ValueError("Every event must have an id.")
        documents.append(("events", event["id"], event))
    return documents


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "store.json",
        help="Path to the local store.json file.",
    )
    parser.add_argument("--project", help="GCP project ID. Defaults to Application Default Credentials.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow importing into a database that already contains users, topics, or events.",
    )
    args = parser.parse_args()

    if not args.source.exists():
        raise SystemExit(f"Source file does not exist: {args.source}")
    with args.source.open(encoding="utf-8") as handle:
        data = json.load(handle)

    db = firestore.Client(project=args.project)
    if not args.overwrite:
        populated = [
            collection
            for collection in ("users", "topics", "events")
            if next(db.collection(collection).limit(1).stream(), None)
        ]
        if populated:
            raise SystemExit(
                f"Firestore already contains data in: {', '.join(populated)}. "
                "Review it first, then rerun with --overwrite if replacing matching document IDs is intentional."
            )

    documents = load_documents(data)
    for group in document_batches(documents):
        batch = db.batch()
        for collection, document_id, value in group:
            batch.set(db.collection(collection).document(document_id), value)
        batch.commit()

    print(f"Imported {len(documents)} documents from {args.source}.")


if __name__ == "__main__":
    main()
