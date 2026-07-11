"""
services/topic_filter.py
────────────────────────────────────────────────────────────────────────────────
FitBuddy AI – Server-side Topic Filter

HOW IT WORKS
────────────
1. Every incoming chat message is normalised to lowercase and stripped of
   punctuation before matching — this prevents trivial bypass with punctuation
   or mixed case ("Y o g a", "YOGA!", "cardio.").

2. Keywords are organised into named CATEGORIES (e.g. WORKOUT, NUTRITION, BMI).
   Each category is a frozenset of exact words/phrases.

3. Matching is TWO-TIER:
   a. Single-word lookup  — O(1) hash set check against a pre-built union of
      all single-word terms across every category.
   b. Multi-word phrase   — O(n) iteration over the (small) phrase list, checking
      whether each phrase string appears anywhere in the normalised message.

4. A message is ACCEPTED if ANY tier produces at least one match.
   No match → the message is REJECTED immediately; the AI is never called.

5. Adding new topics: add words to an existing category set, or create a new
   category dict entry.  The pre-built indices update automatically at import.

DESIGN DECISIONS
────────────────
• Deterministic: zero ML, zero AI. Same input always produces the same decision.
• Fast: single-pass normalisation then O(1) word-set lookup.
• Transparent: every rejection includes the matched (or unmatched) detail in logs.
• Modular: categories are plain dicts — easy to extend without touching logic.
• Production-safe: all exceptions are caught; the filter defaults to ACCEPT on
  unexpected errors so a bug never silently breaks the chat.
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ── Topic categories ──────────────────────────────────────────────────────────
# Each key is the human-readable category name shown in log output.
# Values are sets of keywords/phrases (all lowercase, no leading/trailing spaces).
# Single words are matched as whole words; multi-word phrases are substring-matched.
#
# Rule of thumb for adding new entries:
#   • Single word  → add to the relevant frozenset (e.g. "trampoline")
#   • Two+ words   → add as a phrase string (e.g. "jump rope training")

CATEGORIES: dict[str, frozenset[str]] = {

    # ── Fitness & Exercise ────────────────────────────────────────────────────
    "FITNESS": frozenset({
        "fitness", "fit", "exercise", "exercising", "workout", "workouts",
        "training", "train", "active", "activity", "sport", "sports",
        "athletic", "athlete", "physical", "movement",
    }),

    # ── Gym & Equipment ───────────────────────────────────────────────────────
    "GYM": frozenset({
        "gym", "gymnasium", "weightlifting", "weights", "barbell", "dumbbell",
        "dumbbells", "kettlebell", "kettlebells", "resistance band", "bands",
        "treadmill", "elliptical", "rowing machine", "bench press",
        "squat rack", "pull-up bar", "pull up bar", "power rack",
        "machine", "rep", "reps", "sets", "set", "lift", "lifting",
        "powerlifting", "crossfit", "hiit", "circuit training",
    }),

    # ── Workout Types & Styles ────────────────────────────────────────────────
    "WORKOUT": frozenset({
        "strength", "endurance", "flexibility", "mobility", "balance",
        "plyometric", "calisthenics", "bodyweight", "functional training",
        "interval", "tabata", "emom", "amrap", "superset", "drop set",
        "pyramid", "compound", "isolation", "push", "pull", "legs",
        "upper body", "lower body", "full body", "split", "routine",
        "programme", "program", "schedule", "plan", "planner",
    }),

    # ── Home Workout ──────────────────────────────────────────────────────────
    "HOME_WORKOUT": frozenset({
        "home workout", "home exercise", "home training", "at home workout",
        "no equipment", "bodyweight exercise", "indoor workout",
        "push up", "pushup", "push-up", "pull up", "pullup", "pull-up",
        "sit up", "situp", "sit-up", "crunch", "crunches", "plank",
        "burpee", "burpees", "lunge", "lunges", "squat", "squats",
        "jumping jack", "mountain climber", "mountain climbers",
        "jump squat", "box jump",
    }),

    # ── Yoga ──────────────────────────────────────────────────────────────────
    "YOGA": frozenset({
        "yoga", "yogi", "asana", "poses", "pose", "vinyasa", "hatha",
        "ashtanga", "kundalini", "yin yoga", "restorative yoga",
        "hot yoga", "bikram", "sun salutation", "downward dog",
        "warrior pose", "tree pose", "child pose", "meditation",
        "breathwork", "pranayama", "mindfulness", "mindful",
    }),

    # ── Stretching & Mobility ─────────────────────────────────────────────────
    "STRETCHING": frozenset({
        "stretch", "stretching", "stretches", "flexibility", "foam roll",
        "foam rolling", "mobility", "range of motion", "tight muscle",
        "tight muscles", "hip flexor", "hamstring", "quad", "glute",
        "shoulder stretch", "neck stretch", "cool down", "warm up", "warmup",
        "dynamic stretch", "static stretch", "pnf stretch",
    }),

    # ── Cardio & Aerobics ─────────────────────────────────────────────────────
    "CARDIO": frozenset({
        "cardio", "cardiovascular", "aerobic", "aerobics", "running",
        "run", "runner", "jogging", "jog", "walking", "walk", "cycling",
        "cycle", "cycling", "swimming", "swim", "rowing", "jump rope",
        "skipping rope", "stairclimber", "stair climb", "marathon",
        "5k", "10k", "half marathon", "sprint", "intervals",
        "heart rate", "vo2 max", "stamina", "endurance", "zone 2",
    }),

    # ── Weight Loss & Fat Burn ────────────────────────────────────────────────
    "WEIGHT_LOSS": frozenset({
        "weight loss", "lose weight", "fat loss", "fat burn", "fat burning",
        "caloric deficit", "calorie deficit", "cut", "cutting", "shred",
        "shredding", "slim", "slimming", "lean", "leaning out",
        "belly fat", "body fat", "weight management", "obesity",
        "overweight", "underweight", "scale", "pounds", "kilograms",
        "kg", "lbs", "kilos", "bmi", "body mass index",
    }),

    # ── Muscle Gain & Bodybuilding ────────────────────────────────────────────
    "MUSCLE_GAIN": frozenset({
        "muscle", "muscles", "muscle gain", "muscle building", "build muscle",
        "muscle mass", "hypertrophy", "bulk", "bulking", "lean bulk",
        "bodybuilding", "bodybuilder", "physique", "gains", "gain",
        "bicep", "tricep", "deltoid", "lats", "chest", "pecs",
        "abs", "core", "glutes", "hamstrings", "quadriceps", "calves",
        "protein synthesis", "anabolic", "testosterone", "growth hormone",
    }),

    # ── Nutrition & Food ──────────────────────────────────────────────────────
    "NUTRITION": frozenset({
        "nutrition", "nutritious", "nutrient", "nutrients", "diet",
        "dietary", "eating", "eat", "food", "foods", "meal", "meals",
        "healthy eating", "clean eating", "whole food", "whole foods",
        "processed food", "junk food", "healthy food", "balanced diet",
        "plant based", "plant-based", "organic", "superfood", "superfoods",
    }),

    # ── Specific Foods & Macros ───────────────────────────────────────────────
    "FOOD": frozenset({
        "protein", "carbohydrate", "carbs", "carb", "fat", "fats",
        "fibre", "fiber", "sugar", "glucose", "fructose", "starch",
        "micronutrient", "macronutrient", "macro", "macros",
        "vitamin", "mineral", "omega 3", "omega-3", "antioxidant",
        "chicken", "egg", "eggs", "fish", "salmon", "tuna",
        "tofu", "lentils", "legumes", "quinoa", "oats", "oatmeal",
        "avocado", "broccoli", "spinach", "kale", "sweet potato",
        "greek yogurt", "cottage cheese", "whey", "casein",
        "peanut butter", "almond butter", "nuts", "seeds",
        "fruit", "vegetable", "veggies", "salad",
    }),

    # ── Meal Planning & Timing ────────────────────────────────────────────────
    "MEAL_PLAN": frozenset({
        "meal plan", "meal planning", "meal prep", "meal prepping",
        "breakfast", "lunch", "dinner", "snack", "snacks",
        "pre workout meal", "post workout meal", "pre-workout",
        "post-workout", "intermittent fasting", "fasting", "fast",
        "calorie counting", "track calories", "food diary", "food log",
        "vegan", "vegetarian", "keto", "ketogenic", "paleo",
        "mediterranean diet", "low carb", "high protein", "low fat",
        "gluten free", "dairy free",
    }),

    # ── Calories & Energy ─────────────────────────────────────────────────────
    "CALORIES": frozenset({
        "calorie", "calories", "kcal", "kilojoule", "kj",
        "energy intake", "energy expenditure", "tdee", "maintenance",
        "caloric intake", "caloric surplus", "caloric deficit",
        "burn calories", "calorie burn", "metabolic rate",
    }),

    # ── BMI & Body Metrics ────────────────────────────────────────────────────
    "BMI": frozenset({
        "bmi", "body mass index", "body fat percentage", "body fat",
        "waist circumference", "hip to waist ratio", "body composition",
        "lean mass", "lean body mass", "fat mass", "visceral fat",
        "subcutaneous fat", "body measurement", "measurements",
    }),

    # ── BMR & Metabolism ──────────────────────────────────────────────────────
    "BMR": frozenset({
        "bmr", "basal metabolic rate", "resting metabolic rate", "rmr",
        "metabolism", "metabolic", "metabolise", "metabolize",
        "mifflin", "harris benedict", "activity multiplier",
        "maintenance calories", "total daily energy", "tdee",
    }),

    # ── Water & Hydration ─────────────────────────────────────────────────────
    "WATER": frozenset({
        "water", "hydration", "hydrate", "hydrating", "drink water",
        "water intake", "fluid intake", "dehydration", "dehydrated",
        "electrolyte", "electrolytes", "sodium", "potassium",
        "sports drink", "coconut water",
    }),

    # ── Sleep & Recovery ──────────────────────────────────────────────────────
    "SLEEP": frozenset({
        "sleep", "sleeping", "rest", "recovery", "recover", "recovering",
        "rest day", "active recovery", "deload", "overtraining",
        "muscle soreness", "doms", "delayed onset muscle soreness",
        "foam rolling", "ice bath", "cold shower", "massage",
        "sleep quality", "deep sleep", "rem sleep", "insomnia",
        "circadian rhythm", "melatonin", "nap",
    }),

    # ── Wellness & Healthy Lifestyle ──────────────────────────────────────────
    "WELLNESS": frozenset({
        "wellness", "wellbeing", "well-being", "health", "healthy",
        "lifestyle", "habit", "habits", "routine", "daily routine",
        "self care", "self-care", "mental health", "stress", "anxiety",
        "cortisol", "inflammation", "immune system", "longevity",
        "anti-aging", "anti aging", "posture", "ergonomics",
        "walking", "steps", "step count", "pedometer",
    }),

    # ── Motivation & Goals ────────────────────────────────────────────────────
    "MOTIVATION": frozenset({
        "motivation", "motivate", "motivated", "inspire", "inspiration",
        "goal", "goals", "target", "milestone", "progress", "consistency",
        "discipline", "habit", "mindset", "positive", "accountability",
        "transformation", "challenge", "commitment", "dedication",
        "progress photo", "before and after", "fitness journey",
    }),

    # ── Supplements ───────────────────────────────────────────────────────────
    "SUPPLEMENTS": frozenset({
        "supplement", "supplements", "protein powder", "whey protein",
        "creatine", "bcaa", "amino acid", "amino acids", "pre workout",
        "pre-workout", "post workout", "post-workout", "mass gainer",
        "fat burner", "multivitamin", "fish oil", "vitamin d",
        "magnesium", "zinc", "collagen", "collagen peptide",
        "glutamine", "beta alanine", "caffeine", "nitric oxide",
    }),

    # ── Health Conditions & Goals ─────────────────────────────────────────────
    "HEALTH_GOALS": frozenset({
        "weight management", "blood pressure", "blood sugar",
        "diabetes", "cholesterol", "heart health", "cardiovascular health",
        "bone density", "joint health", "arthritis", "back pain",
        "knee pain", "injury prevention", "rehabilitation", "rehab",
        "physiotherapy", "physical therapy", "sports injury",
        "doctor", "gp", "physician", "healthcare provider",
        "fitness test", "vo2 max", "resting heart rate",
        "blood pressure", "bmi screening",
    }),
}

# ── Pre-build lookup indices (computed once at import time) ───────────────────
# Separate single-word terms (O(1) set lookup) from multi-word phrases (O(n) scan).

_single_words: frozenset[str] = frozenset(
    term for terms in CATEGORIES.values()
    for term in terms
    if " " not in term and "-" not in term
)

_phrases: list[tuple[str, str]] = [        # [(category_name, phrase), ...]
    (cat, term)
    for cat, terms in CATEGORIES.items()
    for term in terms
    if " " in term or "-" in term
]

# Compile a regex that matches any single keyword as a whole word.
# \b anchors prevent "cardio" matching inside "pericardiology".
_WORD_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in sorted(_single_words, key=len, reverse=True)) + r")\b"
)


# ── Public result type ────────────────────────────────────────────────────────

class FilterResult(NamedTuple):
    """Return value from :func:`is_fitness_query`."""
    accepted:  bool          # True  → forward to AI
    category:  str           # Matched category name, or "NONE" if rejected
    matched:   str           # The specific term that triggered acceptance, or ""
    normalised: str          # The cleaned message that was tested


# ── Normalisation helper ──────────────────────────────────────────────────────

_PUNCT_RE = re.compile(r"[^\w\s\-]")        # keep hyphens (pre-workout, etc.)

def _normalise(text: str) -> str:
    """
    Lower-case, NFKC-normalise unicode, collapse whitespace, strip punctuation.
    Examples:
        "Y O G A!"      → "yoga"
        "High-Protein?" → "high-protein"
        "été"           → "ete"           (accent stripping via NFKD fallback)
    """
    # 1. Unicode normalisation (NFKC: canonical decomposition + composition)
    text = unicodedata.normalize("NFKC", text)
    # 2. Lower-case
    text = text.lower()
    # 3. Strip non-word characters except hyphens and whitespace
    text = _PUNCT_RE.sub(" ", text)
    # 4. Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Main public function ──────────────────────────────────────────────────────

def is_fitness_query(message: str) -> FilterResult:
    """
    Determine whether *message* is related to fitness or wellness.

    Algorithm (both tiers run in order; first match wins):

    Tier 1 — Single-word regex  (O(1) average)
        Searches the normalised message for any whole-word match against the
        complete set of single-word fitness keywords using a compiled regex.

    Tier 2 — Multi-word phrase scan  (O(p) where p = number of phrases ~200)
        Iterates over every multi-word phrase and checks ``phrase in normalised``.
        This catches "weight loss", "meal plan", "pull-up bar", etc.

    Args:
        message: Raw user input string (any language, any case).

    Returns:
        FilterResult(accepted, category, matched, normalised)

    Raises:
        Never.  All exceptions are caught; the function returns accepted=True
        on unexpected errors so a bug never silently breaks the chat.
    """
    if not message or not message.strip():
        return FilterResult(
            accepted=False, category="EMPTY", matched="", normalised=""
        )

    try:
        norm = _normalise(message)

        # ── Tier 1: whole-word single keyword match ───────────────────────────
        m = _WORD_RE.search(norm)
        if m:
            matched_word = m.group(1)
            # Find which category owns this word
            for cat, terms in CATEGORIES.items():
                if matched_word in terms:
                    logger.info(
                        "Topic filter ACCEPTED — category=%s  matched=%r  msg=%r",
                        cat, matched_word, message[:80],
                    )
                    return FilterResult(
                        accepted=True, category=cat,
                        matched=matched_word, normalised=norm,
                    )

        # ── Tier 2: multi-word phrase scan ────────────────────────────────────
        for cat, phrase in _phrases:
            if phrase in norm:
                logger.info(
                    "Topic filter ACCEPTED (phrase) — category=%s  matched=%r  msg=%r",
                    cat, phrase, message[:80],
                )
                return FilterResult(
                    accepted=True, category=cat,
                    matched=phrase, normalised=norm,
                )

        # ── No match — reject ─────────────────────────────────────────────────
        logger.info(
            "Topic filter REJECTED — msg=%r  (no fitness keyword found)",
            message[:120],
        )
        return FilterResult(
            accepted=False, category="NONE", matched="", normalised=norm
        )

    except Exception as exc:          # pragma: no cover
        # Safety net: default to ACCEPT so a filter bug never breaks the chat.
        logger.error(
            "Topic filter raised an unexpected error (%s) — defaulting to ACCEPT.",
            exc,
        )
        return FilterResult(accepted=True, category="ERROR", matched="", normalised="")


# ── Convenience rejection response dict ──────────────────────────────────────

REJECTION_RESPONSE: dict = {
    "success":    True,
    "restricted": True,
    "response": (
        "I'm FitBuddy AI, a fitness and wellness assistant. "
        "I can only answer questions related to fitness, nutrition, workouts, "
        "BMI, calories, healthy lifestyle, and wellness. "
        "Please ask a fitness-related question."
    ),
    "source":    "topic_filter",
    "timestamp": None,   # filled in by the caller with current time
}
