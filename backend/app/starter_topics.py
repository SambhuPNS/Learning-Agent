"""Starter topics beyond fractions. Gemini teaches from these lesson plans; the offline tutor builds simple checks from them."""

STARTER_TOPICS = [
    {
        "id": "decimals-percentages",
        "subject": "Mathematics",
        "title": "Decimals & percentages",
        "gradeLevel": 6,
        "description": "Reading decimals as tenths and hundredths, comparing and ordering decimals, and understanding percentages as parts of 100.",
        "lessons": [
            {
                "id": "decimals-tenths-hundredths",
                "title": "Tenths and hundredths",
                "summary": "See how decimals show parts of a whole in tenths and hundredths.",
                "objectives": ["Read and write decimals to two decimal places", "Link decimals to fractions out of 10 and out of 100"],
                "keyIdeas": [
                    "The first digit after the decimal point counts tenths and the second counts hundredths.",
                    "0.3 means 3 tenths (3/10), and 0.07 means 7 hundredths (7/100).",
                    "0.5 and 0.50 are the same amount, because 5 tenths equal 50 hundredths.",
                ],
                "misconceptions": [
                    "Thinking 0.25 is bigger than 0.3 because 25 is bigger than 3",
                    "Reading 0.07 as seven tenths",
                    "Thinking that adding a zero at the end, as in 0.5 to 0.50, makes a decimal bigger",
                ],
            },
            {
                "id": "decimals-comparing",
                "title": "Comparing and ordering decimals",
                "summary": "Put decimals in order by comparing their place values.",
                "objectives": ["Compare two decimals using place value", "Order a set of decimals from smallest to largest"],
                "keyIdeas": [
                    "Compare decimals place by place from the left: ones first, then tenths, then hundredths.",
                    "Writing decimals with the same number of places, such as 0.3 as 0.30, makes them easier to compare.",
                    "On a number line from 0 to 1, decimals sit in order: 0.1, 0.2 and so on up to 0.9.",
                ],
                "misconceptions": [
                    "Thinking a decimal with more digits is always bigger",
                    "Comparing the digits after the point as whole numbers",
                ],
            },
            {
                "id": "percentages-intro",
                "title": "Percentages as parts of 100",
                "summary": "Understand per cent as 'out of 100' and find simple percentages of amounts.",
                "objectives": ["Convert between percentages, fractions and decimals", "Find 10%, 25% and 50% of an amount"],
                "keyIdeas": [
                    "Per cent means 'out of 100', so 35% is 35/100, which is 0.35.",
                    "50% is one half, 25% is one quarter and 10% is one tenth.",
                    "To find 10% of an amount, divide it by 10; other percentages can be built from 10% and 1%.",
                ],
                "misconceptions": [
                    "Thinking 10% of any amount is always 10",
                    "Confusing 0.5% with 50%",
                    "Thinking a percentage can never be more than 100%",
                ],
            },
        ],
    },
    {
        "id": "photosynthesis",
        "subject": "Science",
        "title": "Photosynthesis",
        "gradeLevel": 7,
        "description": "How green plants use light energy to make glucose from carbon dioxide and water, and what changes how fast this happens.",
        "lessons": [
            {
                "id": "photosynthesis-plants-make-food",
                "title": "How plants make food",
                "summary": "Find out what plants need to make their own food.",
                "objectives": ["Name what plants need for photosynthesis", "Explain where in the plant photosynthesis happens"],
                "keyIdeas": [
                    "Plants make their own food, a sugar called glucose, by photosynthesis.",
                    "Photosynthesis needs carbon dioxide from the air, water from the soil and energy from sunlight.",
                    "It happens mainly in the leaves, inside chloroplasts that contain the green pigment chlorophyll.",
                ],
                "misconceptions": [
                    "Thinking plants get their food from the soil",
                    "Thinking plants take in food through their roots",
                    "Thinking chlorophyll is food for the plant",
                ],
            },
            {
                "id": "photosynthesis-equation",
                "title": "The photosynthesis equation",
                "summary": "Use the word equation to show what goes in and what comes out.",
                "objectives": ["Write the word equation for photosynthesis", "Explain what happens to the oxygen produced"],
                "keyIdeas": [
                    "Word equation: carbon dioxide + water → glucose + oxygen, using light energy.",
                    "Light energy is captured by chlorophyll; it is not a substance that gets used up.",
                    "Oxygen is released as a by-product through tiny pores in the leaf called stomata.",
                ],
                "misconceptions": [
                    "Thinking plants take in oxygen and give out carbon dioxide during photosynthesis",
                    "Thinking sunlight is a substance used up in the reaction",
                    "Thinking plants only photosynthesise and never respire",
                ],
            },
            {
                "id": "photosynthesis-factors",
                "title": "What affects photosynthesis",
                "summary": "Explore how light, carbon dioxide and temperature change the rate.",
                "objectives": ["Describe how light intensity affects the rate", "Explain what a limiting factor is"],
                "keyIdeas": [
                    "More light, more carbon dioxide and a warmer temperature speed up photosynthesis, up to a limit.",
                    "Whichever factor is in shortest supply limits the rate; this is called a limiting factor.",
                    "If it gets too hot, the plant's enzymes are damaged and the rate falls.",
                ],
                "misconceptions": [
                    "Thinking more light always makes photosynthesis faster, without any limit",
                    "Thinking temperature has no effect on photosynthesis",
                ],
            },
        ],
    },
    {
        "id": "water-cycle",
        "subject": "Science",
        "title": "The water cycle",
        "gradeLevel": 5,
        "description": "How water moves between oceans, the air and the land through evaporation, condensation, precipitation and collection.",
        "lessons": [
            {
                "id": "water-cycle-evaporation-condensation",
                "title": "Evaporation and condensation",
                "summary": "See how water turns into vapour and back into droplets.",
                "objectives": ["Explain evaporation and condensation", "Describe how clouds form"],
                "keyIdeas": [
                    "The Sun heats water in oceans, lakes and rivers, and it evaporates into water vapour, an invisible gas.",
                    "As water vapour rises it cools and condenses into tiny droplets that form clouds.",
                    "Condensation is the opposite of evaporation: a gas turns back into a liquid.",
                ],
                "misconceptions": [
                    "Thinking clouds are made of water vapour rather than tiny droplets of water or ice",
                    "Thinking water only evaporates when it boils",
                    "Thinking the steam you can see is water vapour",
                ],
            },
            {
                "id": "water-cycle-precipitation",
                "title": "Precipitation and collection",
                "summary": "Follow water from the clouds back to the ground and the sea.",
                "objectives": ["Name the types of precipitation", "Describe where water collects"],
                "keyIdeas": [
                    "When cloud droplets join and become too heavy, they fall as precipitation: rain, snow, sleet or hail.",
                    "Water collects in oceans, rivers and lakes, and soaks underground as groundwater.",
                    "Water that flows over the land back to rivers and seas is called run-off.",
                ],
                "misconceptions": [
                    "Thinking rain falls because clouds burst",
                    "Thinking all rainwater soaks into the ground",
                ],
            },
            {
                "id": "water-cycle-whole",
                "title": "The whole cycle",
                "summary": "Put every stage together into one continuous cycle.",
                "objectives": ["Sequence the stages of the water cycle", "Explain what drives the cycle"],
                "keyIdeas": [
                    "Evaporation, condensation, precipitation and collection repeat in a continuous cycle.",
                    "The Sun's energy drives the cycle, and gravity brings water back down.",
                    "Plants also release water vapour from their leaves; this is called transpiration.",
                ],
                "misconceptions": [
                    "Thinking the water cycle has a fixed start and end",
                    "Thinking the water cycle makes new water instead of reusing the same water",
                ],
            },
        ],
    },
    {
        "id": "parts-of-speech",
        "subject": "English",
        "title": "Parts of speech",
        "gradeLevel": 5,
        "description": "Recognising nouns, pronouns, verbs, adverbs and adjectives, and how they work together in sentences.",
        "lessons": [
            {
                "id": "parts-of-speech-nouns-pronouns",
                "title": "Nouns and pronouns",
                "summary": "Spot the words that name things and the words that replace them.",
                "objectives": ["Identify common and proper nouns", "Use pronouns to avoid repeating nouns"],
                "keyIdeas": [
                    "A noun names a person, place, thing or idea, such as teacher, India, ball or happiness.",
                    "A proper noun names a particular person or place and starts with a capital letter.",
                    "A pronoun such as he, she, it or they replaces a noun so we don't repeat it.",
                ],
                "misconceptions": [
                    "Thinking nouns can only be things you can touch",
                    "Forgetting capital letters on proper nouns",
                    "Using a pronoun before it is clear which noun it replaces",
                ],
            },
            {
                "id": "parts-of-speech-verbs-adverbs",
                "title": "Verbs and adverbs",
                "summary": "Find the action in a sentence and the words that describe it.",
                "objectives": ["Identify action and being verbs", "Use adverbs to say how, when or where"],
                "keyIdeas": [
                    "A verb shows an action, like run or write, or a state of being, like is or seem.",
                    "Verbs change form to show time: walk, walked, will walk.",
                    "An adverb describes a verb, often telling how, when or where, like quickly, yesterday or here.",
                ],
                "misconceptions": [
                    "Thinking 'is' and 'are' are not verbs",
                    "Thinking every word ending in -ly is an adverb, when 'friendly' is an adjective",
                ],
            },
            {
                "id": "parts-of-speech-adjectives",
                "title": "Adjectives",
                "summary": "Use describing words and compare with them correctly.",
                "objectives": ["Identify adjectives in a sentence", "Form comparative and superlative adjectives"],
                "keyIdeas": [
                    "An adjective describes a noun: a tall tree, three apples, a happy dog.",
                    "To compare, add -er and -est (tall, taller, tallest); for longer words use more and most.",
                    "To find adjectives in a sentence, find the noun first, then ask which words describe it.",
                ],
                "misconceptions": [
                    "Saying 'more taller' instead of 'taller'",
                    "Mixing up adjectives and adverbs, as in 'a quick runner' and 'runs quickly'",
                ],
            },
        ],
    },
]
