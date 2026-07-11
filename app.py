"""
FitBuddy AI – Flask Application
────────────────────────────────────────────────────────────────────────────
All AI responses are routed through services/orchestrate.py which implements
a three-layer fallback:
  1. IBM watsonx Orchestrate External Chat API  (ORCHESTRATE_API_KEY)
  2. IBM watsonx.ai Chat API  (IBM_CLOUD_API_KEY + WATSONX_PROJECT_ID)
  3. Built-in rule-based fitness knowledge base (always available)

Credentials are loaded exclusively from the .env file via python-dotenv.
No secret is present in this source file.
────────────────────────────────────────────────────────────────────────────
"""

import logging
import os
import random
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session

# Load .env before anything reads os.environ
load_dotenv()

# Import services AFTER load_dotenv so env vars are present at import time
from services.orchestrate import get_chat_response, health_check as _ai_health, log_startup_status as _log_startup
from services.topic_filter import REJECTION_RESPONSE, is_fitness_query

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if os.environ.get("FLASK_ENV") == "development" else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-dev-key-change-me")

# Print AI layer status once at startup (non-blocking; failures are logged only)
with app.app_context():
    try:
        _log_startup()
    except Exception:
        pass

# ── Fitness data ───────────────────────────────────────────────────────────────
WORKOUTS = {
    "weight_loss": {
        "beginner":     ["Monday: 30-min brisk walk", "Tuesday: Bodyweight squats 3×15, Push-ups 3×10", "Wednesday: Rest / light yoga", "Thursday: 30-min cycling", "Friday: Plank 3×30s, Lunges 3×12", "Saturday: 45-min walk", "Sunday: Rest"],
        "intermediate": ["Monday: 45-min jog + core workout", "Tuesday: HIIT 20 min + strength circuit", "Wednesday: Yoga / mobility", "Thursday: Cycling 45 min", "Friday: Full-body strength training", "Saturday: 5K run", "Sunday: Rest"],
        "advanced":     ["Monday: 5K run + heavy squats", "Tuesday: HIIT 30 min + upper body", "Wednesday: Tempo run 8K", "Thursday: Lower body strength", "Friday: CrossFit-style WOD", "Saturday: Long run 10K", "Sunday: Active recovery"],
    },
    "muscle_gain": {
        "beginner":     ["Monday: Push (chest, shoulders, triceps)", "Tuesday: Pull (back, biceps)", "Wednesday: Legs + core", "Thursday: Rest", "Friday: Push day", "Saturday: Pull day", "Sunday: Rest"],
        "intermediate": ["Monday: Chest + triceps (heavy)", "Tuesday: Back + biceps (heavy)", "Wednesday: Legs (squat focus)", "Thursday: Shoulders + arms", "Friday: Full-body compound lifts", "Saturday: Active recovery / cardio", "Sunday: Rest"],
        "advanced":     ["Monday: Chest (volume)", "Tuesday: Back (volume)", "Wednesday: Legs (heavy)", "Thursday: Shoulders + arms", "Friday: Power lifts (deadlift/bench)", "Saturday: Hypertrophy circuit", "Sunday: Rest"],
    },
    "endurance": {
        "beginner":     ["Monday: 20-min easy jog", "Tuesday: Rest", "Wednesday: 25-min walk/run intervals", "Thursday: Yoga", "Friday: 30-min cycling", "Saturday: 35-min easy jog", "Sunday: Rest"],
        "intermediate": ["Monday: 5K easy run", "Tuesday: Cross-training 45 min", "Wednesday: Tempo run 4K", "Thursday: Strength + core", "Friday: Interval run (400m × 6)", "Saturday: Long run 8K", "Sunday: Rest"],
        "advanced":     ["Monday: 8K easy", "Tuesday: Hill repeats", "Wednesday: 10K tempo", "Thursday: Strength training", "Friday: Speed work (800m × 5)", "Saturday: Long run 15K", "Sunday: Rest"],
    },
    "flexibility": {
        "beginner":     ["Monday: 20-min full-body stretch", "Tuesday: Yoga basics 30 min", "Wednesday: Foam rolling 20 min", "Thursday: Pilates beginner 30 min", "Friday: Hip & shoulder stretch", "Saturday: Gentle yoga 45 min", "Sunday: Rest"],
        "intermediate": ["Monday: Yoga flow 45 min", "Tuesday: Deep stretch 30 min", "Wednesday: Pilates core 40 min", "Thursday: Mobility drills", "Friday: Yin yoga 45 min", "Saturday: Full-body flexibility 60 min", "Sunday: Rest"],
        "advanced":     ["Monday: Advanced yoga 60 min", "Tuesday: Contortion stretching 45 min", "Wednesday: Pilates advanced 50 min", "Thursday: Dance flexibility", "Friday: Splits progression", "Saturday: Full flexibility session 75 min", "Sunday: Rest"],
    },
}

NUTRITION = {
    "vegetarian": {
        "breakfast": ["Oatmeal with berries & nuts", "Whole-grain toast + avocado + eggs", "Greek yogurt parfait with granola", "Smoothie bowl (banana, spinach, almond milk)"],
        "lunch":     ["Quinoa Buddha bowl with chickpeas", "Lentil soup + whole-grain bread", "Caprese salad + pasta primavera", "Veggie wrap with hummus"],
        "dinner":    ["Paneer tikka + brown rice + dal", "Vegetable stir-fry with tofu", "Black bean tacos + Mexican rice", "Mushroom risotto + side salad"],
        "snacks":    ["Apple + almond butter", "Mixed nuts & dried fruits", "Hummus + veggie sticks", "Cheese + whole-grain crackers"],
    },
    "non_vegetarian": {
        "breakfast": ["Scrambled eggs + turkey bacon", "Greek yogurt + honey + berries", "Protein smoothie (whey, banana, milk)", "Omelette with vegetables + whole-grain toast"],
        "lunch":     ["Grilled chicken salad", "Tuna sandwich on whole grain", "Chicken and vegetable soup", "Turkey and avocado wrap"],
        "dinner":    ["Baked salmon + quinoa + steamed broccoli", "Grilled chicken breast + sweet potato + green beans", "Beef stir-fry + brown rice", "Shrimp pasta with olive oil & garlic"],
        "snacks":    ["Hard-boiled eggs", "Cottage cheese + pineapple", "Chicken jerky", "Greek yogurt"],
    },
    "vegan": {
        "breakfast": ["Chia pudding with almond milk & berries", "Smoothie (spinach, banana, oat milk)", "Avocado toast + nutritional yeast", "Overnight oats with plant milk"],
        "lunch":     ["Chickpea salad wrap", "Black bean & corn salad", "Lentil curry + basmati rice", "Falafel pita with tahini"],
        "dinner":    ["Tofu stir-fry + edamame + brown rice", "Lentil bolognese with pasta", "Vegan burger + sweet potato fries", "Butternut squash soup + crusty bread"],
        "snacks":    ["Trail mix (nuts, seeds, dried fruit)", "Rice cakes with nut butter", "Roasted chickpeas", "Fruit salad"],
    },
}

QUOTES = [
    "The body achieves what the mind believes.",
    "Fitness is not about being better than someone else. It's about being better than you used to be.",
    "Take care of your body. It's the only place you have to live.",
    "The pain you feel today will be the strength you feel tomorrow.",
    "Push yourself, because no one else is going to do it for you.",
    "Great things never come from comfort zones.",
    "Dream it. Believe it. Build it.",
    "Your only limit is you.",
    "Fall in love with taking care of yourself — mind, body, spirit.",
    "Success is usually the culmination of controlling failure.",
]

FITNESS_TIPS = [
    "Warm up for 5–10 minutes before every workout to prevent injury.",
    "Compound exercises (squats, deadlifts, bench press) burn more calories and build more muscle.",
    "Progressive overload: gradually increase weight, reps, or duration to keep improving.",
    "Rest is as important as exercise — muscles grow during recovery, not during training.",
    "Track your meals for at least 2 weeks to understand your eating habits.",
    "Morning workouts boost energy and metabolism for the entire day.",
    "Strength training increases resting metabolic rate by up to 15%.",
    "Consistency over intensity — a moderate workout done daily beats an extreme workout once a week.",
]

HEALTHY_HABITS = [
    "Drink a glass of water immediately after waking up.",
    "Prepare your workout clothes the night before.",
    "Take the stairs instead of the elevator.",
    "Do 10 min of stretching before bed.",
    "Eat slowly and mindfully — it takes 20 min for your brain to register fullness.",
    "Get 7–9 hours of quality sleep every night.",
    "Limit screen time 1 hour before bed.",
    "Practice gratitude — mental health directly impacts physical health.",
]

CHALLENGES = [
    {"title": "Plank Challenge",    "description": "Hold a plank for 60 seconds. Rest 30s. Repeat 3 times.",                  "difficulty": "Beginner"},
    {"title": "100 Squats",         "description": "Complete 100 bodyweight squats throughout the day.",                        "difficulty": "Intermediate"},
    {"title": "5K Walk/Run",        "description": "Complete a 5K walk or run at any pace.",                                    "difficulty": "Beginner"},
    {"title": "Push-up Pyramid",    "description": "1, 2, 3… up to 10, then back down. Total: 100 push-ups.",                   "difficulty": "Advanced"},
    {"title": "Hydration Challenge","description": "Drink 3 litres of water today. Track every glass.",                         "difficulty": "Beginner"},
    {"title": "Burpee EMOM",        "description": "Every minute on the minute: 10 burpees for 10 minutes.",                    "difficulty": "Advanced"},
]


# ── Page Routes ────────────────────────────────────────────────────────────────

@app.route("/favicon.ico")
def favicon():
    from flask import redirect, url_for
    return redirect(url_for("static", filename="images/favicon.svg"))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat")
def chat():
    if "chat_history" not in session:
        session["chat_history"] = []
    return render_template("chat.html", chat_history=session["chat_history"])

@app.route("/workout")
def workout():
    return render_template("workout.html")

@app.route("/nutrition")
def nutrition():
    return render_template("nutrition.html")

@app.route("/bmi")
def bmi():
    return render_template("bmi.html")

@app.route("/calories")
def calories():
    return render_template("calories.html")

@app.route("/water")
def water():
    return render_template("water.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/motivation")
def motivation():
    return render_template(
        "motivation.html",
        quote=random.choice(QUOTES),
        tip=random.choice(FITNESS_TIPS),
        habit=random.choice(HEALTHY_HABITS),
        challenge=random.choice(CHALLENGES),
        all_tips=FITNESS_TIPS,
        all_habits=HEALTHY_HABITS,
        all_challenges=CHALLENGES,
    )

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")


# ── AI Chat API ────────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Forward the user's message to IBM watsonx Orchestrate (or watsonx.ai fallback)
    and return the AI response.

    Request JSON:
        { "message": "user's text" }

    Response JSON:
        {
            "response":  str,          # AI reply
            "source":    str,          # "orchestrate" | "watsonx_ai" | "fallback"
            "timestamp": str           # HH:MM
        }
    """
    data    = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "Message is required."}), 400
    if len(message) > 2000:
        return jsonify({"error": "Message too long (max 2000 characters)."}), 400

    # ── Topic filter — must run BEFORE any AI call ────────────────────────────
    # Deterministic keyword/phrase matching; no AI or network involved.
    # Rejected messages never reach watsonx Orchestrate or watsonx.ai.
    filter_result = is_fitness_query(message)
    if not filter_result.accepted:
        rejection = dict(REJECTION_RESPONSE)
        rejection["timestamp"] = datetime.now().strftime("%H:%M")
        return jsonify(rejection), 200

    # Pass prior conversation turns for multi-turn context
    history: list[dict] = session.get("chat_history", [])

    result = get_chat_response(message, history)

    # Persist turns to session (keep last 20 turns = 10 exchanges)
    if "chat_history" not in session:
        session["chat_history"] = []
    session["chat_history"].append({"role": "user",      "content": message})
    session["chat_history"].append({"role": "assistant", "content": result["response"]})
    session["chat_history"] = session["chat_history"][-20:]
    session.modified = True

    # Log at DEBUG when the expected Orchestrate→watsonx.ai fallback occurs.
    # Only escalate to WARNING for genuinely unexpected errors.
    if result.get("error"):
        err_msg  = result["error"]
        expected = (
            "not set" in err_msg
            or "[404]" in err_msg
            or ("[500]" in err_msg and "11112E" in err_msg)
        )
        if expected and result["source"] in ("watsonx_ai", "fallback"):
            logger.debug("Using %s (Orchestrate layer not active yet).", result["source"])
        else:
            logger.warning("AI fallback active (%s): %s", result["source"], err_msg)

    return jsonify({
        "response":  result["response"],
        "source":    result["source"],
        "timestamp": datetime.now().strftime("%H:%M"),
    })


@app.route("/api/chat/clear", methods=["POST"])
def api_chat_clear():
    session.pop("chat_history", None)
    return jsonify({"status": "cleared"})


# ── Health Check ───────────────────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def api_health():
    """Probe AI integration layers — useful for deployment verification."""
    return jsonify({
        "status": "ok",
        "ai":     _ai_health(),
    })


# ── Fitness Tool APIs ──────────────────────────────────────────────────────────

@app.route("/api/workout", methods=["POST"])
def api_workout():
    data     = request.get_json(silent=True) or {}
    goal     = data.get("goal", "weight_loss")
    level    = data.get("level", "beginner")
    duration = int(data.get("duration", 30))
    plan     = WORKOUTS.get(goal, WORKOUTS["weight_loss"]).get(level, [])
    adjusted = []
    for day in plan:
        if duration <= 20:
            day = day.replace("45-min", "20-min").replace("30-min", "20-min").replace("60 min", "20 min")
        elif duration >= 60:
            day = day.replace("20-min", "45-min").replace("30-min", "60-min").replace("45 min", "60 min")
        adjusted.append(day)
    return jsonify({"plan": adjusted, "goal": goal, "level": level, "duration": duration})


@app.route("/api/nutrition", methods=["POST"])
def api_nutrition():
    data     = request.get_json(silent=True) or {}
    diet     = data.get("diet", "vegetarian")
    plan_key = diet.replace("-", "_")
    plan     = NUTRITION.get(plan_key, NUTRITION["vegetarian"])
    return jsonify({"plan": plan, "diet": diet})


@app.route("/api/bmi", methods=["POST"])
def api_bmi():
    data = request.get_json(silent=True) or {}
    try:
        height_cm = float(data.get("height", 0))
        weight_kg = float(data.get("weight", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid input."}), 400
    if height_cm <= 0 or weight_kg <= 0:
        return jsonify({"error": "Height and weight must be positive."}), 400

    height_m = height_cm / 100
    bmi      = round(weight_kg / (height_m ** 2), 1)

    if bmi < 18.5:
        category   = "Underweight"
        suggestion = "You are underweight. Increase caloric intake with nutrient-dense foods and consider strength training to build muscle mass."
        color      = "#3b82f6"
    elif bmi < 25:
        category   = "Normal Weight"
        suggestion = "Great job! Maintain your healthy weight with balanced nutrition and regular exercise. Aim for 150 min of moderate activity weekly."
        color      = "#22c55e"
    elif bmi < 30:
        category   = "Overweight"
        suggestion = "A moderate caloric deficit (300–500 kcal/day) and 30 min of daily exercise can help you reach a healthy weight."
        color      = "#f59e0b"
    else:
        category   = "Obese"
        suggestion = "Please consult a healthcare provider. A supervised weight-loss programme combining diet, exercise, and lifestyle changes is recommended."
        color      = "#ef4444"

    return jsonify({"bmi": bmi, "category": category, "suggestion": suggestion, "color": color})


@app.route("/api/calories", methods=["POST"])
def api_calories():
    data = request.get_json(silent=True) or {}
    try:
        age      = int(data.get("age", 0))
        gender   = data.get("gender", "male")
        height   = float(data.get("height", 0))
        weight   = float(data.get("weight", 0))
        activity = data.get("activity", "sedentary")
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid input."}), 400

    bmr = (10 * weight + 6.25 * height - 5 * age + 5) if gender == "male" \
        else (10 * weight + 6.25 * height - 5 * age - 161)

    multipliers = {
        "sedentary": 1.2, "light": 1.375, "moderate": 1.55,
        "active": 1.725, "very_active": 1.9,
    }
    tdee = round(bmr * multipliers.get(activity, 1.2))
    return jsonify({
        "bmr":         round(bmr),
        "tdee":        tdee,
        "weight_loss": round(tdee - 500),
        "weight_gain": round(tdee + 300),
        "activity":    activity,
    })


@app.route("/api/water", methods=["POST"])
def api_water():
    data = request.get_json(silent=True) or {}
    try:
        weight   = float(data.get("weight", 0))
        activity = data.get("activity", "moderate")
        climate  = data.get("climate", "temperate")
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid input."}), 400

    base_ml  = weight * 35
    base_ml += {"sedentary": 0, "light": 250, "moderate": 500, "active": 750, "very_active": 1000}.get(activity, 500)
    base_ml += {"cold": -250, "temperate": 0, "warm": 250, "hot": 500}.get(climate, 0)
    total_ml = round(base_ml)
    return jsonify({
        "ml":      total_ml,
        "liters":  round(total_ml / 1000, 1),
        "glasses": round(total_ml / 250),
    })


@app.route("/api/contact", methods=["POST"])
def api_contact():
    data    = request.get_json(silent=True) or {}
    name    = data.get("name",    "").strip()
    email   = data.get("email",   "").strip()
    subject = data.get("subject", "").strip()
    message = data.get("message", "").strip()
    if not all([name, email, subject, message]):
        return jsonify({"error": "All fields are required."}), 400
    if "@" not in email:
        return jsonify({"error": "Invalid email address."}), 400
    return jsonify({"status": "success", "message": f"Thank you {name}! We'll get back to you shortly."})


@app.route("/api/motivation/refresh", methods=["GET"])
def api_motivation_refresh():
    return jsonify({
        "quote":     random.choice(QUOTES),
        "tip":       random.choice(FITNESS_TIPS),
        "habit":     random.choice(HEALTHY_HABITS),
        "challenge": random.choice(CHALLENGES),
    })


# ── Run ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port  = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV", "production") == "development"
    logger.info("Starting FitBuddy AI on port %d (debug=%s)", port, debug)
    app.run(host="0.0.0.0", port=port, debug=debug)
