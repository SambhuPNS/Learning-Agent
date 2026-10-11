"""Seed content: the Fractions topic is loaded into the topic store on first run, like any teacher-created topic.
The hand-written `script` for each lesson is only used as an offline fallback when Gemini is unavailable."""

SEED_TOPIC_ID = "fractions"


def _teach(title, paragraphs, speech, visual=None, strategy=None):
    return {"kind": "teach", "title": title, "paragraphs": paragraphs, "speech": speech, "visual": visual,
            "strategy": strategy or ("visual" if visual else "step-by-step")}


def _question(title, intro, prompt, answers, hint, explain_again, correct, wrong, *, options=None, visual=None, speech=None):
    return {
        "kind": "question",
        "title": title,
        "paragraphs": intro,
        "speech": speech or " ".join(intro + [prompt]),
        "visual": visual,
        "question": {
            "prompt": prompt,
            "format": "choice" if options else "text",
            "options": options or [],
            "expectedAnswer": answers[0],
            "acceptableAnswers": answers,
            "hint": hint,
        },
        "explainAgain": explain_again,
        "correctMessage": correct,
        "wrongMessage": wrong,
    }


def _summary(paragraphs, speech):
    return {"kind": "summary", "title": "Lesson complete", "paragraphs": paragraphs, "speech": speech, "visual": None}


def _visual(kind, fractions, caption):
    return {
        "type": kind,
        "fractions": [{"numerator": n, "denominator": d, "label": f"{n}/{d}"} for n, d in fractions],
        "items": [],
        "caption": caption,
    }


def _text(text):
    return {"type": "text", "text": text}


def _callout(label, text):
    return {"type": "callout", "caption": label, "text": text}


def _flow(caption, steps):
    return {"type": "flow", "caption": caption, "items": [{"label": label, "detail": detail} for label, detail in steps]}


def _bar_chart(caption, bars, y_label):
    return {"type": "bar-chart", "caption": caption, "data": [{"label": label, "value": value} for label, value in bars],
            "yLabel": y_label}


def _line_graph(caption, points, x_label, y_label):
    return {"type": "line-graph", "caption": caption, "points": [{"x": x, "y": y} for x, y in points],
            "xLabel": x_label, "yLabel": y_label}


def _table(caption, columns, rows):
    return {"type": "table", "caption": caption, "columns": columns, "rows": rows}


def _rich_teach(title, blocks, speech):
    """A teach step made of ordered blocks, in the same format Gemini returns."""
    visuals = [block for block in blocks if block["type"] not in ("text", "callout")]
    return {"kind": "teach", "title": title, "blocks": blocks,
            "paragraphs": [block["text"] for block in blocks if block["type"] in ("text", "callout")],
            "speech": speech, "visual": visuals[0] if visuals else None,
            "strategy": "visual" if visuals else "step-by-step"}


LESSONS = {
    "fraction-basics": {
        "id": "fraction-basics",
        "topicId": "fractions",
        "order": 1,
        "title": "What is a fraction?",
        "summary": "Numerators, denominators and equal parts.",
        "context": {
            "objectives": [
                "Explain that a fraction names equal parts of one whole",
                "Identify the numerator and denominator and what each means",
                "Write a fraction from a picture or a story",
            ],
            "keyIdeas": [
                "The denominator (bottom) is how many equal parts the whole is split into",
                "The numerator (top) is how many of those parts we are talking about",
                "The parts must be equal in size",
            ],
            "misconceptions": [
                "Swapping numerator and denominator",
                "Counting unequal pieces as fractions",
                "Thinking the denominator counts the unshaded parts",
            ],
        },
        "script": [
            _rich_teach(
                "A fraction names part of a whole",
                [
                    _text("A fraction tells us about equal parts of one whole thing, like a pizza or a chocolate bar."),
                    _visual("fraction-circles", [(3, 4)], "3 of 4 equal slices are shaded"),
                    _text("In 3/4, the pizza is cut into 4 equal slices and we have 3 of them. Each number in a fraction has its own job."),
                    _table("The two numbers in 3/4", ["Number", "Name", "What it tells us"], [
                        ["3 (top)", "Numerator", "How many of the parts we have"],
                        ["4 (bottom)", "Denominator", "How many equal parts make the whole"],
                    ]),
                    _callout("Remember", "Bottom: how many equal parts. Top: how many of them we have."),
                ],
                "A fraction tells us about equal parts of one whole. The bottom number, the denominator, says how many equal parts the whole is cut into. The top number, the numerator, says how many of those parts we have. So three quarters means four equal slices, and we have three of them.",
            ),
            _teach(
                "The parts must be equal",
                [
                    "Fractions only work when every part is the same size.",
                    "This bar is split into 5 equal parts and 2 of them are shaded, so it shows 2/5.",
                    "If the pieces were different sizes, we could not call one piece a fifth.",
                ],
                "Fractions only work when every part is the same size. This bar is split into five equal parts, and two are shaded. So it shows two fifths.",
                _visual("fraction-bars", [(2, 5)], "2 of 5 equal parts are shaded"),
            ),
            _question(
                "Your turn",
                ["Let's check that idea with a story."],
                "A chocolate bar is split into 8 equal pieces. You eat 3 of them. What fraction of the bar did you eat?",
                ["3/8"],
                "Count all the equal pieces for the bottom number, then the pieces you ate for the top number.",
                [
                    "Think of the bar as 8 equal squares. That 8 goes on the bottom because it is the whole.",
                    "You ate 3 squares, so 3 goes on top.",
                ],
                "Exactly! 8 equal pieces make the whole, and you ate 3, so you ate 3/8.",
                "Not quite. The whole bar has 8 equal pieces, so the denominator is 8.",
                speech="A chocolate bar is split into eight equal pieces. You eat three of them. What fraction of the bar did you eat?",
            ),
            _question(
                "Quick check",
                ["Now let's think about what the numbers mean."],
                "In the fraction 5/6, what does the 6 tell us?",
                ["How many equal parts make the whole"],
                "The bottom number describes the whole.",
                ["In 5/6 the bottom number is 6. The bottom number always tells how many equal parts the whole is cut into."],
                "Yes! The denominator, 6, tells us the whole is cut into 6 equal parts.",
                "Not quite. The 6 is the denominator, the bottom number.",
                options=["How many parts are shaded", "How many equal parts make the whole", "How many wholes there are"],
                speech="In the fraction five sixths, what does the six tell us?",
            ),
            _question(
                "Read the picture",
                ["Look carefully at the circle."],
                "What fraction of the circle is shaded?",
                ["2/3"],
                "Count all the equal parts first, then count the shaded ones.",
                ["The circle has 3 equal parts in total, so 3 goes on the bottom. Now count how many are shaded for the top."],
                "Perfect! 2 of the 3 equal parts are shaded, so it is 2/3.",
                "Not quite. Count the total number of equal parts for the bottom number.",
                visual=_visual("fraction-circles", [(2, 3)], "How much is shaded?"),
                speech="Look at the circle. What fraction of the circle is shaded?",
            ),
            _summary(
                [
                    "Great work! You now know that a fraction describes equal parts of a whole.",
                    "The denominator tells how many equal parts make the whole, and the numerator tells how many we are talking about.",
                ],
                "Great work! You now know that a fraction describes equal parts of a whole. The denominator tells how many equal parts make the whole, and the numerator tells how many we are talking about.",
            ),
        ],
    },
    "equivalent-fractions": {
        "id": "equivalent-fractions",
        "topicId": "fractions",
        "order": 2,
        "title": "Equivalent fractions",
        "summary": "Different names for the same amount.",
        "context": {
            "objectives": [
                "Recognise that different fractions can show the same amount",
                "Make equivalent fractions by multiplying or dividing top and bottom by the same number",
                "Simplify a fraction to its simplest form",
            ],
            "keyIdeas": [
                "Equivalent fractions name the same amount",
                "Multiply or divide the numerator and denominator by the same number",
                "A fraction is in simplest form when top and bottom share no common factor except 1",
            ],
            "misconceptions": [
                "Adding the same number to top and bottom",
                "Only changing the numerator or only the denominator",
            ],
        },
        "script": [
            _teach(
                "Same amount, different names",
                [
                    "Look at these three bars. They are the same size, and the same amount is shaded in each.",
                    "1/2, 2/4 and 4/8 all show exactly half. Fractions that show the same amount are called equivalent fractions.",
                ],
                "Look at these three bars. The same amount is shaded in each one. One half, two quarters and four eighths all show exactly half. We call these equivalent fractions.",
                _visual("fraction-bars", [(1, 2), (2, 4), (4, 8)], "Each bar shows the same amount"),
            ),
            _rich_teach(
                "How to make an equivalent fraction",
                [
                    _text("To make an equivalent fraction, multiply the top and bottom by the same number."),
                    _text("For 2/3, multiply both by 2: 2 x 2 = 4 and 3 x 2 = 6. So 2/3 = 4/6."),
                    _visual("fraction-circles", [(2, 3), (4, 6)], "2/3 and 4/6 cover the same amount"),
                    _text("Cutting every slice into 2 smaller slices doubles both numbers, but the amount stays the same. You can keep going:"),
                    _table("Equivalent fractions of 2/3", ["Multiply top and bottom by", "Equivalent fraction"],
                           [["2", "4/6"], ["3", "6/9"], ["4", "8/12"]]),
                    _callout("Rule", "Whatever you do to the top, do the same to the bottom."),
                ],
                "To make an equivalent fraction, multiply the top and the bottom by the same number. Two thirds times two over two gives four sixths. Every slice is cut in half, so both numbers double, but the amount stays the same. Six ninths and eight twelfths are equal to two thirds too.",
            ),
            _question(
                "Fill the gap",
                ["Let's try one."],
                "Complete this: 1/3 = ?/6. What number goes on top?",
                ["2", "2/6"],
                "What did you multiply 3 by to get 6? Do the same to the top.",
                ["3 became 6, so the bottom was multiplied by 2. Multiply the top, 1, by 2 as well."],
                "Yes! 1 x 2 = 2, so 1/3 = 2/6.",
                "Not quite. The bottom was multiplied by 2, so the top must be too.",
                speech="Complete this: one third equals how many sixths? What number goes on top?",
            ),
            _question(
                "Spot the match",
                ["Which one shows the same amount?"],
                "Which fraction is equal to 3/4?",
                ["6/8"],
                "Try multiplying the top and bottom of 3/4 by 2.",
                ["Multiply both parts of 3/4 by 2: 3 x 2 = 6 and 4 x 2 = 8."],
                "Correct! 3/4 = 6/8 because both numbers were multiplied by 2.",
                "Not quite. Check which choice is 3/4 with top and bottom multiplied by the same number.",
                options=["6/8", "3/8", "4/6"],
                speech="Which fraction is equal to three quarters?",
            ),
            _question(
                "Simplify it",
                ["Now go the other way and make the numbers smaller."],
                "Write 4/8 in its simplest form.",
                ["1/2"],
                "Which number divides both 4 and 8 exactly? Try the biggest one.",
                ["Both 4 and 8 can be divided by 4. 4 divided by 4 is 1, and 8 divided by 4 is 2."],
                "Brilliant! 4/8 simplifies to 1/2.",
                "Not quite. Divide the top and bottom by the same number until you cannot go further.",
                speech="Write four eighths in its simplest form.",
            ),
            _summary(
                [
                    "Excellent! Equivalent fractions show the same amount with different numbers.",
                    "Multiply or divide the top and bottom by the same number to find them, and divide to simplify.",
                ],
                "Excellent! Equivalent fractions show the same amount with different numbers. Multiply or divide the top and bottom by the same number to find them.",
            ),
        ],
    },
    "comparing-fractions": {
        "id": "comparing-fractions",
        "topicId": "fractions",
        "order": 3,
        "title": "Comparing fractions",
        "summary": "Decide which fraction is bigger.",
        "context": {
            "objectives": [
                "Compare fractions with the same denominator",
                "Compare fractions with the same numerator",
                "Compare fractions with different denominators using a common denominator",
            ],
            "keyIdeas": [
                "Same denominator: the bigger numerator is the bigger fraction",
                "Same numerator: fewer parts means bigger parts, so the smaller denominator is bigger",
                "Different denominators: rewrite both with a common denominator, then compare numerators",
            ],
            "misconceptions": [
                "Thinking a bigger denominator means a bigger fraction",
                "Comparing only the numerators when denominators differ",
            ],
        },
        "script": [
            _teach(
                "When the bottoms match",
                [
                    "If two fractions have the same denominator, their parts are the same size.",
                    "So we just compare the numerators. 3/5 is bigger than 2/5 because 3 parts are more than 2 parts of the same size.",
                ],
                "If two fractions have the same denominator, their parts are the same size. So we just compare the top numbers. Three fifths is bigger than two fifths.",
                _visual("fraction-bars", [(3, 5), (2, 5)], "Same-sized parts: 3 parts beat 2 parts"),
            ),
            _rich_teach(
                "When the tops match",
                [
                    _text("Now look at 1/2 and 1/3. Both have one part shaded."),
                    _visual("fraction-circles", [(1, 2), (1, 3)], "Fewer pieces means bigger pieces"),
                    _text("A whole cut into 2 pieces has bigger pieces than a whole cut into 3. So 1/2 is bigger than 1/3."),
                    _text("Here is the same idea with a 120 cm ribbon. The more equal pieces you cut, the shorter each piece gets."),
                    _bar_chart("One piece of a 120 cm ribbon", [("1/2", 60), ("1/3", 40), ("1/5", 24), ("1/8", 15)],
                               "Length of one piece (cm)"),
                    _callout("Remember", "When the numerators match, the smaller denominator wins."),
                ],
                "Now look at one half and one third. A whole cut into two pieces has bigger pieces than a whole cut into three. The chart shows a ribbon: the more pieces you cut, the shorter each one. So when the top numbers match, the smaller bottom number gives the bigger fraction.",
            ),
            _question(
                "Your turn",
                ["Use what you just saw."],
                "Which is larger: 1/4 or 1/6?",
                ["1/4"],
                "Both have 1 part. Which whole is cut into fewer, bigger pieces?",
                ["Imagine sharing a cake with 4 friends or with 6 friends. With fewer friends, each slice is bigger."],
                "Correct! Quarters are bigger than sixths, so 1/4 is larger.",
                "Not quite. Remember: a bigger denominator means the whole is cut into more, smaller pieces.",
                options=["1/4", "1/6"],
                speech="Which is larger: one quarter or one sixth?",
            ),
            _question(
                "Same-size parts",
                ["These two share a denominator."],
                "Which is larger: 3/8 or 5/8?",
                ["5/8"],
                "The pieces are the same size. Who has more pieces?",
                ["Both are eighths, so every piece is the same size. 5 pieces are more than 3 pieces."],
                "Yes! 5 eighths is more than 3 eighths.",
                "Not quite. With the same denominator, compare the top numbers.",
                options=["3/8", "5/8"],
                speech="Which is larger: three eighths or five eighths?",
            ),
            _teach(
                "When nothing matches",
                [
                    "What about 1/2 and 3/5? Neither the tops nor the bottoms match.",
                    "Rewrite both with the same denominator. 10 works for both: 1/2 = 5/10 and 3/5 = 6/10.",
                    "Now the parts are the same size, and 6/10 is bigger, so 3/5 is bigger than 1/2.",
                ],
                "What about one half and three fifths? Rewrite both with the same denominator. Ten works for both. One half is five tenths, and three fifths is six tenths. So three fifths is bigger.",
                _visual("fraction-bars", [(5, 10), (6, 10)], "Rewritten as tenths: 5/10 and 6/10"),
            ),
            _question(
                "Challenge",
                ["Try a common denominator. 12 works well here."],
                "Which is larger: 2/3 or 3/4?",
                ["3/4"],
                "Change both into twelfths. Multiply 2/3 by 4/4 and 3/4 by 3/3.",
                ["2/3 = 8/12 and 3/4 = 9/12. Now compare the tops."],
                "Brilliant! 2/3 = 8/12 and 3/4 = 9/12, so 3/4 is larger.",
                "Not quite. Rewrite both fractions as twelfths, then compare.",
                options=["2/3", "3/4", "They are equal"],
                speech="Which is larger: two thirds or three quarters?",
            ),
            _summary(
                [
                    "You did it! Same denominator: compare the tops. Same numerator: the smaller bottom wins.",
                    "Different denominators: make a common denominator first, then compare.",
                ],
                "You did it! Same denominator, compare the tops. Same numerator, the smaller bottom wins. Different denominators, make them match first.",
            ),
        ],
    },
    "adding-fractions": {
        "id": "adding-fractions",
        "topicId": "fractions",
        "order": 4,
        "title": "Adding & subtracting",
        "summary": "Combine fractions with the same denominator.",
        "context": {
            "objectives": [
                "Add fractions with the same denominator",
                "Subtract fractions with the same denominator",
                "Solve simple word problems with fractions",
            ],
            "keyIdeas": [
                "With the same denominator, add or subtract the numerators",
                "The denominator stays the same because the size of the parts does not change",
            ],
            "misconceptions": [
                "Adding the denominators too, for example 1/5 + 2/5 = 3/10",
            ],
        },
        "script": [
            _rich_teach(
                "Adding same-size parts",
                [
                    _text("When fractions have the same denominator, the parts are the same size."),
                    _text("So we add the numerators and keep the denominator: 1/5 + 2/5 = 3/5."),
                    _visual("fraction-bars", [(1, 5), (2, 5), (3, 5)], "1/5 + 2/5 = 3/5"),
                    _flow("Adding fractions with the same denominator", [
                        ("Check", "Are the denominators the same?"),
                        ("Add", "Add the numerators: 1 + 2 = 3"),
                        ("Keep", "Keep the denominator, so the answer is 3/5"),
                    ]),
                    _callout("Watch out", "Never add the denominators. 1/5 + 2/5 is not 3/10."),
                ],
                "When fractions have the same denominator, the parts are the same size. So we add the top numbers and keep the bottom number. One fifth plus two fifths is three fifths. Check the bottoms match, add the tops, and keep the bottom. Never add the bottom numbers.",
            ),
            _rich_teach(
                "Why the bottom stays the same",
                [
                    _text("The denominator tells the size of each part. Adding more fifths still gives you fifths."),
                    _text("Sam reads 1/8 of a book every day. Each day adds one more eighth, so the number of eighths grows while the bottom number stays 8."),
                    _line_graph("Sam reads 1/8 of the book each day", [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)],
                                "Day", "Eighths of the book read"),
                    _text("Subtracting works the same way: 5/8 - 2/8 = 3/8."),
                    _visual("fraction-circles", [(5, 8), (3, 8)], "5/8 take away 2/8 leaves 3/8"),
                ],
                "The bottom number tells the size of each part. Adding more fifths still gives you fifths. If Sam reads one eighth of a book every day, the eighths add up one at a time, but they are always eighths. Subtracting works the same way: five eighths take away two eighths is three eighths.",
            ),
            _question(
                "Your turn",
                ["Add these."],
                "What is 2/7 + 3/7?",
                ["5/7"],
                "Add the top numbers. Keep the bottom number.",
                ["You have 2 sevenths and 3 more sevenths. Count them: 5 sevenths."],
                "Correct! 2 + 3 = 5, so the answer is 5/7.",
                "Not quite. Only the numerators are added. The denominator stays 7.",
                speech="What is two sevenths plus three sevenths?",
            ),
            _question(
                "Take away",
                ["Now subtract."],
                "What is 7/9 - 4/9?",
                ["3/9", "1/3"],
                "Subtract the top numbers. Keep the bottom number.",
                ["Start with 7 ninths and take 4 ninths away. 3 ninths are left."],
                "Yes! 7 - 4 = 3, so it is 3/9, which also simplifies to 1/3.",
                "Not quite. Subtract only the numerators and keep 9 on the bottom.",
                speech="What is seven ninths minus four ninths?",
            ),
            _question(
                "Pizza problem",
                ["A real-life one."],
                "Riya ate 1/4 of a pizza and Sam ate 2/4. How much did they eat together?",
                ["3/4"],
                "They are both quarters. Add the quarters together.",
                ["1 quarter plus 2 quarters is 3 quarters. The slices are still quarters."],
                "Delicious and correct! Together they ate 3/4.",
                "Not quite. Do not add the denominators. The slices are still quarters.",
                options=["3/8", "3/4", "2/4"],
                speech="Riya ate one quarter of a pizza and Sam ate two quarters. How much did they eat together?",
            ),
            _summary(
                [
                    "Fantastic! To add or subtract fractions with the same denominator, work with the numerators.",
                    "The denominator stays the same because the size of each part does not change.",
                ],
                "Fantastic! To add or subtract fractions with the same denominator, work with the top numbers and keep the bottom number the same.",
            ),
        ],
    },
}


def seed_topics(created_at: str) -> list[dict]:
    lessons = [
        {"id": lesson["id"], "title": lesson["title"], "summary": lesson["summary"], **lesson["context"]}
        for lesson in sorted(LESSONS.values(), key=lambda item: item["order"])
    ]
    return [{
        "id": SEED_TOPIC_ID,
        "subject": "Mathematics",
        "title": "Fractions",
        "gradeLevel": 7,
        "description": "Understanding fractions as equal parts of a whole, equivalent fractions, comparing fractions and adding or subtracting fractions with the same denominator.",
        "createdBy": "system",
        "createdByName": "Brightpath starter content",
        "createdAt": created_at,
        "published": True,
        "lessons": lessons,
    }]


SCRIPTS = {lesson_id: lesson["script"] for lesson_id, lesson in LESSONS.items()}
