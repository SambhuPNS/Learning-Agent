"""Load demo sign-ins and a synthetic class with about two weeks of learning history.

Run from backend/. It writes to the same storage as the app: data/store.json, or Firestore when
FIRESTORE_ENABLED=true and GOOGLE_CLOUD_PROJECT are set (with Application Default Credentials).

    .venv/bin/python scripts/seed_demo.py --password 'choose-a-password'

Creates anything that is missing (running it again skips existing accounts):
  - a teacher and two students who sign in with --password (first.last@<--email-domain>),
  - a class of synthetic students (they cannot sign in) whose progress fills the teacher dashboard,
  - the starter topics.
Each synthetic answer goes through the real student model, so mastery, teaching-style scores and
misconceptions are consistent with what the tutor would have recorded.
"""

import argparse
import hashlib
import math
import random
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import auth, student_model, topics, tutor  # noqa: E402
from app.config import TEACHER_INVITE_CODE  # noqa: E402
from app.curriculum import seed_topics  # noqa: E402
from app.store import store  # noqa: E402

# The .example domain is reserved, so these addresses can never belong to a real person or Google account.
EMAIL_DOMAIN = "lakeview.example"
TEACHER = "Priya Menon"
STUDENT = "Riya Sharma"
NEW_STUDENT = "Kiran Rao"
CLASS = [
    ("Aarav Mehta", 7), ("Diya Iyer", 7), ("Kabir Singh", 6), ("Ananya Rao", 7), ("Rohan Das", 8), ("Meera Nair", 6),
    ("Arjun Patel", 7), ("Saanvi Gupta", 7), ("Vihaan Kumar", 6), ("Ishita Banerjee", 8), ("Yuki Tanaka", 7), ("Liam Chen", 7),
]
INTERESTS = ["Football", "Cricket", "Music", "Gaming", "Cooking", "Space", "Animals", "Art", "Dance", "Movies"]
STUDENT_QUESTIONS = {
    "Mathematics": ["Why do we need a common denominator?", "Is 0.5 the same as one half?", "Can a fraction be bigger than 1?",
                    "How do I know which fraction is bigger?"],
    "Science": ["Do plants breathe at night?", "Why are leaves green?", "Where does the water in clouds come from?"],
    "English": ["Is 'happiness' a noun?", "How do I know if a word is an adverb?"],
}


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def lesson(topic_id: str, index: int) -> tuple[dict, dict]:
    topic = next(t for t in store.all_topics() if t["id"] == topic_id)
    return topic, topic["lessons"][index]


def wrong_answer(question: dict, rng: random.Random) -> str:
    others = [option for option in question.get("options", []) if option != question["expectedAnswer"]]
    if others:
        return rng.choice(others)
    expected = question["expectedAnswer"]
    if "/" in expected:
        top, bottom = expected.split("/", 1)
        return f"{bottom}/{top}" if top != bottom else f"{top}/{int(bottom) + 1}"
    return "I'm not sure"


class Simulation:
    """Plays one student through lessons, recording events exactly as the tutor would."""

    def __init__(self, user: dict, rng: random.Random, ability: float, best_style: str, start: datetime,
                 style_effect: float = 0.12) -> None:
        self.user, self.rng, self.ability, self.best_style, self.style_effect = user, rng, ability, best_style, style_effect
        self.model = student_model._new_model()
        self.clock = start
        self.last_event_at = start
        self.lessons: list[tuple[dict, dict, dict, list[dict], dict]] = []

    def _event(self, events: list[dict], event_type: str, base: dict, **data) -> None:
        self.clock += timedelta(seconds=self.rng.uniform(15, 60))
        self.last_event_at = self.clock
        events.append({"id": uuid.uuid4().hex[:12], "ts": iso(self.clock), "userId": self.user["id"], "type": event_type, **base, **data})

    def play(self, topic: dict, item: dict, finish: bool = True, max_answers: int = 12) -> None:
        rng, model = self.rng, self.model
        base = {"lessonId": item["id"], "topicId": topic["id"]}
        prior = student_model.prior_mastery(self.user, topic)
        student_model.concept(model, item["id"], prior)
        self_reported = self.user["profile"]["learningStyle"]
        script = topics.fallback_script(item)
        teach_titles = [step["title"] for step in script if step["kind"] == "teach"] or [item["title"]]
        questions = [step["question"] for step in script if step.get("question")]
        events: list[dict] = []
        self._event(events, "lesson_started", base)
        correct = wrong = 0
        stop_after = max_answers if finish else rng.randint(2, 4)
        for attempt in range(stop_after):
            if correct >= tutor.TARGET_CORRECT:
                break
            strategy = student_model.choose_strategy(model, self_reported)
            student_model.record_strategy_use(model, strategy)
            self._event(events, "tutor_step", base, kind="teach", title=teach_titles[attempt % len(teach_titles)],
                        strategy=strategy, source="gemini", hasQuestion=False)
            if strategy != self.best_style and rng.random() < 0.35 * (1.2 - self.ability):
                student_model.record_signal(model, "explain_again", strategy=strategy)
                self._event(events, "explain_again", base, strategy=strategy, inputMode="choice")
                strategy = student_model.choose_strategy(model, self_reported, exclude=strategy)
                student_model.record_strategy_use(model, strategy)
                self._event(events, "tutor_step", base, kind="teach", title="Another way to see it", strategy=strategy,
                            source="gemini", hasQuestion=False)
            question = questions[attempt % len(questions)]
            used_hint = rng.random() < 0.4 * (1 - self.ability)
            if used_hint:
                student_model.record_signal(model, "hint")
                self._event(events, "hint", base, question=question["prompt"], waitedMs=int(rng.uniform(8000, 30000)))
            mastery = model["concepts"][item["id"]]["mastery"]
            chance = 0.12 + 0.35 * mastery + 0.45 * self.ability + (self.style_effect if strategy == self.best_style else 0) + (0.1 if used_hint else 0)
            is_correct = rng.random() < min(0.95, max(0.08, chance))
            response_ms = int(rng.lognormvariate(math.log(7000 / (0.5 + self.ability)), 0.4))
            input_mode = rng.choice(["choice", "choice", "typed", "voice"])
            misconception = None
            if not is_correct and item.get("misconceptions") and rng.random() < 0.85:
                misconception = rng.choice(item["misconceptions"][:2])
            result = student_model.record_answer(model, item["id"], prior, correct=is_correct, used_hint=used_hint,
                                                 response_ms=response_ms, strategy=strategy, input_mode=input_mode,
                                                 misconception=misconception)
            self._event(events, "answer", base, question=question["prompt"],
                        answer=question["expectedAnswer"] if is_correct else wrong_answer(question, rng), correct=is_correct,
                        responseMs=response_ms, slow=result["slow"], inputMode=input_mode, usedHint=used_hint, attempt=1,
                        strategy=strategy, misconception=misconception, mastery=result["mastery"])
            correct, wrong = correct + is_correct, wrong + (not is_correct)
            if rng.random() < 0.12:
                student_model.record_signal(model, "ask")
                self._event(events, "question_asked", base, text=rng.choice(STUDENT_QUESTIONS.get(topic["subject"], ["Can you show me an example?"])),
                            inputMode=rng.choice(["typed", "voice"]))
        complete = correct >= tutor.TARGET_CORRECT
        mastery_pct = round(model["concepts"][item["id"]]["mastery"] * 100)
        if complete:
            self._event(events, "lesson_completed", base, mastery=mastery_pct)
        model["concepts"][item["id"]]["lastSeen"] = iso(self.clock)
        model["updatedAt"] = iso(self.clock)
        session = {**tutor._new_session(item["id"], topic["id"]), "correct": correct, "wrong": wrong, "complete": complete}
        self.lessons.append((topic, item, {"mastery": mastery_pct, "complete": complete, "started": True}, events, session))
        # The next lesson happens on a later day.
        self.clock += timedelta(days=rng.randint(1, 2), hours=rng.uniform(-3, 3))

    def end_at(self, moment: datetime) -> None:
        """Shifts the whole history so that the last activity happened at `moment`."""
        delta = moment - self.last_event_at
        for _, _, _, events, _ in self.lessons:
            for event in events:
                event["ts"] = iso(datetime.fromisoformat(event["ts"]) + delta)
        for item in self.model["concepts"].values():
            item["lastSeen"] = iso(datetime.fromisoformat(item["lastSeen"]) + delta)
        self.model["updatedAt"] = iso(moment)

    def save(self) -> None:
        for topic, item, progress, events, session in self.lessons:
            key = tutor._session_key(self.user["id"], item["id"])
            _, _, _, version = store.get_learning_state(self.user["id"], key, student_model._new_model)
            store.commit_learning_turn(self.user["id"], key, version, self.model, session, progress, events)


def profile_for(grade: int, rng: random.Random) -> dict:
    return {"grade": grade, "mathConfidence": rng.randint(2, 5), "fractionsComfort": rng.choice(["new", "some", "some", "confident"]),
            "learningStyle": rng.choice(student_model.STRATEGIES), "pace": rng.choice(["slow", "steady", "steady", "fast"]),
            "interests": rng.sample(INTERESTS, 3), "voiceEnabled": True}


def ensure_starter_topics() -> None:
    existing = {topic["id"] for topic in store.all_topics()}
    for topic in seed_topics(iso(datetime.now(timezone.utc))):
        if topic["id"] not in existing:
            store.save_topic(topic)
            print(f"  added topic {topic['title']}")


def email_for(name: str, domain: str) -> str:
    return f"{'.'.join(name.lower().split())}@{domain}"


def sign_up(name: str, domain: str, password: str, role: str) -> dict | None:
    email = email_for(name, domain)
    if store.find_user_by_email(email):
        print(f"  {email} already exists, skipped")
        return None
    _, user = auth.signup(name, email, password, role, TEACHER_INVITE_CODE)
    print(f"  created {role} {email}")
    return user


def class_student(name: str, domain: str) -> dict | None:
    email = email_for(name, domain)
    if store.find_user_by_email(email):
        return None
    user = {"id": uuid.uuid4().hex, "name": name, "email": email, "role": "student", "seeded": True,
            "createdAt": iso(datetime.now(timezone.utc) - timedelta(days=16)), "profile": None, "progress": {}}
    # No password and an unguessable token: these learners exist only to fill the class dashboards.
    store.create_user(user, hashlib.sha256(secrets.token_bytes(32)).hexdigest())
    return user


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--password", required=True, help="Password for the teacher and the two students who can sign in (8+ characters).")
    parser.add_argument("--email-domain", default=EMAIL_DOMAIN, help=f"Domain for the generated addresses (default {EMAIL_DOMAIN}).")
    parser.add_argument("--seed", type=int, default=2026, help="Random seed, so the synthetic class is reproducible.")
    args = parser.parse_args()
    if len(args.password) < 8:
        parser.error("--password must be at least 8 characters")
    rng = random.Random(args.seed)
    now = datetime.now(timezone.utc)

    print("Topics")
    ensure_starter_topics()

    domain = args.email_domain
    print("Sign-ins")
    sign_up(TEACHER, domain, args.password, "teacher")
    sign_up(NEW_STUDENT, domain, args.password, "student")
    student = sign_up(STUDENT, domain, args.password, "student")
    if student:
        student["profile"] = {"grade": 7, "mathConfidence": 3, "fractionsComfort": "some", "learningStyle": "visual",
                              "pace": "steady", "interests": ["Cricket", "Space", "Music"], "voiceEnabled": True}
        store.save_profile(student["id"], student["profile"])
        # Picked sign-up style "visual", but real-life examples work better: the dashboards show the tutor noticing.
        sim = Simulation(student, rng, ability=0.7, best_style="real-world", start=now - timedelta(days=9), style_effect=0.3)
        sim.play(*lesson("fractions", 0))
        sim.play(*lesson("fractions", 1))
        sim.play(*lesson("fractions", 2), finish=False)
        sim.play(*lesson("decimals-percentages", 0), finish=False)
        sim.end_at(now - timedelta(hours=20))
        sim.save()

    print("Class")
    created = 0
    # A spread of abilities: the weakest few stall early, so the dashboard has learners who need support.
    abilities = [0.12, 0.2, 0.3, 0.42, 0.5, 0.58, 0.65, 0.7, 0.76, 0.82, 0.88, 0.93]
    rng.shuffle(abilities)
    for (name, grade), ability in zip(CLASS, abilities):
        user = class_student(name, domain)
        if not user:
            continue
        user["profile"] = profile_for(grade, rng)
        store.save_profile(user["id"], user["profile"])
        best_style = rng.choice(student_model.STRATEGIES)
        sim = Simulation(user, rng, ability, best_style, start=now - timedelta(days=20))
        if ability < 0.35:
            sim.play(*lesson("fractions", 0), finish=False)
            sim.play(*lesson("fractions", 1), finish=False)
        else:
            plan = [("fractions", 0), ("fractions", 1), ("fractions", 2), ("fractions", 3)][: 1 + int(ability * 3.5)]
            for position, (topic_id, index) in enumerate(plan):
                sim.play(*lesson(topic_id, index), finish=position < len(plan) - 1 or rng.random() < ability)
            extra = rng.choice(["decimals-percentages", "photosynthesis", "water-cycle", "parts-of-speech", None])
            if extra:
                sim.play(*lesson(extra, 0), finish=rng.random() < ability)
        sim.end_at(now - timedelta(hours=rng.uniform(2, 120 if ability < 0.35 else 72)))
        sim.save()
        created += 1
    print(f"  created {created} class students")

    print("\nSign in with (password as given):")
    for name, role in ((TEACHER, "teacher"), (STUDENT, "student with history"), (NEW_STUDENT, "new student")):
        print(f"  {email_for(name, domain):28} {role}")


if __name__ == "__main__":
    main()
