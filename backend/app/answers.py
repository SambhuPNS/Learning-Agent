"""Rule-based answer normalisation and intent detection used for grading and the offline voice fallback."""

import re

NUMBER_WORDS = {
    "zero": 0, "one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
DENOMINATOR_WORDS = {
    "half": 2, "halves": 2, "third": 3, "thirds": 3, "quarter": 4, "quarters": 4, "fourth": 4,
    "fourths": 4, "fifth": 5, "fifths": 5, "sixth": 6, "sixths": 6, "seventh": 7, "sevenths": 7,
    "eighth": 8, "eighths": 8, "ninth": 9, "ninths": 9, "tenth": 10, "tenths": 10,
    "eleventh": 11, "elevenths": 11, "twelfth": 12, "twelfths": 12,
}
ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "last": -1}


def _tokens(text: str) -> list[str]:
    lowered = re.sub(r"\b(over|out of|divided by)\b", " / ", text.lower())
    return re.findall(r"\d+|/|[a-z]+", lowered)


def extract_fraction(text: str) -> str | None:
    words = [str(NUMBER_WORDS[w]) if w in NUMBER_WORDS else w for w in _tokens(text)]
    for i, word in enumerate(words):
        if not word.isdigit():
            continue
        if i + 2 < len(words) and words[i + 1] == "/" and words[i + 2].isdigit():
            return f"{int(word)}/{int(words[i + 2])}"
        if i + 1 < len(words) and words[i + 1] in DENOMINATOR_WORDS:
            return f"{int(word)}/{DENOMINATOR_WORDS[words[i + 1]]}"
    if "half" in words:
        return "1/2"
    return None


def _plain(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9/]+", text.lower()))


def resolve_choice(text: str, options: list[str]) -> str | None:
    if not options:
        return None
    plain = _plain(text)
    for option in options:
        if _plain(option) == plain:
            return option
    fraction = extract_fraction(text)
    if fraction:
        for option in options:
            if extract_fraction(option) == fraction:
                return option
    for word, index in ORDINALS.items():
        if re.search(rf"\b{word}\b", plain) and abs(index) <= len(options):
            if word == "third" and fraction:
                continue
            return options[index]
    spoken = set(plain.split())
    best, best_score = None, 0.0
    for option in options:
        option_words = set(_plain(option).split())
        if option_words:
            score = len(spoken & option_words) / len(option_words)
            if score > best_score:
                best, best_score = option, score
    return best if best_score >= 0.6 else None


def normalise_answer(text: str, question: dict | None) -> str:
    options = (question or {}).get("options") or []
    choice = resolve_choice(text, options)
    if choice:
        return choice
    fraction = extract_fraction(text)
    if fraction:
        return fraction
    numbers = re.findall(r"\d+", text)
    words = [NUMBER_WORDS[w] for w in _tokens(text) if w in NUMBER_WORDS and w not in ("a", "an")]
    if len(numbers) == 1:
        return numbers[0]
    if not numbers and len(words) == 1:
        return str(words[0])
    return text.strip()


def matches(answer: str, question: dict) -> bool:
    candidate = _plain(normalise_answer(answer, question))
    return any(candidate == _plain(accepted) for accepted in question.get("acceptableAnswers", []))


HINT_WORDS = ("hint", "clue", "help me", "stuck")
EXPLAIN_WORDS = ("explain", "again", "don't understand", "dont understand", "do not understand", "confused", "another way", "didn't get", "didnt get")
CONTINUE_WORDS = ("next", "continue", "ready", "go on", "move on", "okay", "ok", "got it", "yes", "sure", "let's go")
QUESTION_STARTS = ("why", "how", "what", "can", "could", "is", "does", "do", "when", "where", "who")


def interpret(transcript: str, question: dict | None) -> dict:
    text = transcript.strip()
    lowered = text.lower()
    result = {"transcript": text, "intent": "unclear", "answer": "", "question": ""}
    if not text:
        return result
    if any(word in lowered for word in HINT_WORDS):
        result["intent"] = "hint"
        return result
    if any(word in lowered for word in EXPLAIN_WORDS):
        result["intent"] = "explain_again"
        return result
    if question:
        normalised = normalise_answer(text, question)
        looks_like_question = lowered.endswith("?") or lowered.split()[0] in QUESTION_STARTS
        if normalised != text.strip() or not looks_like_question:
            result.update(intent="answer", answer=normalised)
            return result
        result.update(intent="ask", question=text)
        return result
    if any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in CONTINUE_WORDS) and len(lowered.split()) <= 6:
        result["intent"] = "continue"
        return result
    result.update(intent="ask", question=text)
    return result
