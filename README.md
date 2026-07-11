# FitBuddy AI – Personal Fitness & Wellness Coach

> **Production-ready** AI-powered fitness and wellness web application built with Python Flask, Bootstrap 5, and Chart.js — with live IBM watsonx.ai (LLaMA 3.3 70B) responses and full IBM watsonx Orchestrate integration wired and ready to activate.

---

## 🚀 Features

| Feature | Description |
|---|---|
| 🤖 AI Chat | ChatGPT-style fitness coach — live IBM watsonx.ai responses, Orchestrate-ready |
| 🛡️ Topic Filter | Server-side fitness-only topic guard (21 categories, 532 keywords) |
| 🏋️ Workout Planner | Custom 7-day schedules by goal, fitness level, and duration |
| 🥗 Nutrition Planner | Meal plans for vegetarian, non-vegetarian, and vegan diets |
| ⚖️ BMI Calculator | BMI gauge, category, ideal weight range, health suggestion |
| 🔥 Calorie Calculator | BMR + TDEE via Mifflin–St Jeor, macro breakdown |
| 💧 Water Intake Calculator | Daily hydration with activity and climate adjustment |
| 📊 Progress Dashboard | 5 interactive Chart.js charts |
| 💪 Motivation | Daily quotes, tips, habits, and challenges with refresh API |
| ℹ️ About | IBM watsonx Orchestrate & IBM Cloud Lite explanation |
| 📬 Contact | Validated contact form with FAQ accordion |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11+, Flask 3.0, python-dotenv |
| **Frontend** | HTML5, CSS3, Bootstrap 5.3, Bootstrap Icons |
| **Charts** | Chart.js 4 (line, bar, doughnut) |
| **AI — Layer 1** | IBM watsonx Orchestrate (agent: `ebea739a-784d-43d1-a90b-5b06d8591404`) |
| **AI — Layer 2** | IBM watsonx.ai `meta-llama/llama-3-3-70b-instruct` ← **active now** |
| **AI — Layer 3** | Built-in rule-based fitness knowledge base (zero network) |
| **Topic Filter** | Deterministic keyword/regex guard — 21 categories, 532 terms |
| **Deployment** | IBM Cloud Lite, Gunicorn, Heroku/Render compatible |

---

## 📦 Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-username/fitbuddy-ai.git
cd fitbuddy-ai

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate           # Windows
source venv/bin/activate        # Linux / macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment template and fill in credentials
cp .env.example .env
# Edit .env with your IBM Cloud credentials (see below)

# 5. Run the application
python app.py
```

Open your browser at **http://localhost:5000**

---

## ⚙️ Environment Variables

Copy `.env.example` to `.env` and set each value:

```env
# Flask
SECRET_KEY=your-long-random-secret-key
FLASK_ENV=development

# IBM watsonx Orchestrate service credential (from IBM Cloud → Service credentials)
ORCHESTRATE_API_KEY=your-orchestrate-service-credential-apikey
ORCHESTRATE_URL=https://api.au-syd.watson-orchestrate.cloud.ibm.com/instances/your-instance-id

# Agent GUID from the WXO UI browser URL (/build/agent/edit/<guid>)
ORCHESTRATE_AGENT_ID=your-agent-guid

# IBM Cloud account key (for watsonx.ai fallback)
IBM_CLOUD_API_KEY=your-ibm-cloud-account-api-key

# watsonx.ai project
WATSONX_PROJECT_ID=your-watsonx-project-id
WATSONX_AI_URL=https://au-syd.ml.cloud.ibm.com
WATSONX_CHAT_MODEL=meta-llama/llama-3-3-70b-instruct
```

> **Never commit `.env` to source control.** It is listed in `.gitignore`.

---

## 🔗 IBM watsonx Integration

### 3-Layer AI Fallback Architecture

```
User message
     │
     ▼  [Topic Filter]  ← server-side, before any AI call
     │   21 categories · 532 keywords · deterministic regex
     │   Non-fitness? → reject immediately, no AI called
     │
     ▼  Layer 1: IBM watsonx Orchestrate
     │   POST https://api.au-syd.watson-orchestrate.cloud.ibm.com/v1/chat
     │   agent_id: ebea739a-784d-43d1-a90b-5b06d8591404
     │   Status: ready once agent is Published in WXO UI
     │   ↓ (404/500 if agent not published → fall through)
     │
     ▼  Layer 2: IBM watsonx.ai Chat API  ← ACTIVE NOW
     │   POST https://au-syd.ml.cloud.ibm.com/ml/v1/text/chat
     │   Model: meta-llama/llama-3-3-70b-instruct
     │   ↓ (network error → fall through)
     │
     ▼  Layer 3: Built-in Knowledge Base
         21 topic categories · always available · no network needed
```

### Activate Layer 1 — Publish the FitBuddy AI Agent

The agent GUID is already configured. It needs to be **Published** in the WXO UI:

1. Go to **[au-syd.watson-orchestrate.cloud.ibm.com](https://au-syd.watson-orchestrate.cloud.ibm.com)**
2. Open the **FitBuddy AI** agent
3. Click **Preview** — confirm it responds correctly
4. Click **Publish** (top-right) — agent state changes from `Draft` → `Published`
5. Restart Flask — the startup banner will show `Layer 1 Orchestrate: ready`

**No code changes needed.** Everything is already wired.

### Current Integration Status

| Variable | Status | Value |
|---|---|---|
| `ORCHESTRATE_API_KEY` | ✅ Set | Service credential key |
| `ORCHESTRATE_URL` | ✅ Set | `https://api.au-syd.watson-orchestrate.cloud.ibm.com/instances/2ea226e0-...` |
| `ORCHESTRATE_AGENT_ID` | ✅ Set | `ebea739a-784d-43d1-a90b-5b06d8591404` |
| `IBM_CLOUD_API_KEY` | ✅ Set | Account-level key |
| `WATSONX_PROJECT_ID` | ✅ Set | `f8aa1369-b14a-4ff5-...` |
| `WATSONX_CHAT_MODEL` | ✅ Set | `meta-llama/llama-3-3-70b-instruct` |

### Startup Status Banner

Every time `python app.py` runs, the integration status is logged:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FitBuddy AI — Integration Status
  Layer 1  Orchestrate : agent_not_published — publish agent in WXO UI
           Agent ID    : ebea739a-784d-43d1-a90b-5b06d8591404
  Layer 2  watsonx.ai  : ready (model: meta-llama/llama-3-3-70b-instruct)
  Layer 3  Fallback KB : ready
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

After publishing the agent:
```
  Layer 1  Orchestrate : ready
```

### Health Check Endpoint

```bash
GET /api/health
```

Returns live status of all three AI layers:

```json
{
  "status": "ok",
  "ai": {
    "orchestrate": "agent_not_published — ...",
    "orchestrate_agent_id": "ebea739a-784d-43d1-a90b-5b06d8591404",
    "watsonx_ai": "ready (model: meta-llama/llama-3-3-70b-instruct)",
    "fallback": "ready"
  }
}
```

---

## 🛡️ Topic Filter

All chat messages are validated **server-side** before any AI call.

```
Non-fitness message → 200 JSON { "restricted": true, "response": "I'm FitBuddy AI..." }
Fitness message     → forwarded to AI layers
```

**21 categories enforced:**

| Category | Sample keywords |
|---|---|
| FITNESS | fitness, exercise, training, active |
| GYM | gym, barbell, dumbbell, bench press |
| WORKOUT | strength, hiit, circuit, routine, programme |
| HOME_WORKOUT | push-up, plank, squat, burpee, lunge |
| YOGA | yoga, asana, vinyasa, meditation, pranayama |
| STRETCHING | stretch, foam rolling, mobility, warm up |
| CARDIO | cardio, running, cycling, heart rate, vo2 max |
| WEIGHT_LOSS | fat loss, caloric deficit, bmi, shredding |
| MUSCLE_GAIN | hypertrophy, bulk, bodybuilding, gains |
| NUTRITION | nutrition, diet, healthy eating, whole food |
| FOOD | protein, carbs, omega-3, chicken, quinoa |
| MEAL_PLAN | meal prep, intermittent fasting, keto, vegan |
| CALORIES | calories, kcal, tdee, caloric surplus |
| BMI | bmi, body mass index, body fat percentage |
| BMR | bmr, basal metabolic rate, metabolism |
| WATER | water, hydration, electrolytes, dehydration |
| SLEEP | sleep, recovery, doms, deload |
| WELLNESS | wellness, healthy, lifestyle, self-care |
| MOTIVATION | motivation, goal, progress, discipline |
| SUPPLEMENTS | creatine, bcaa, whey protein, pre-workout |
| HEALTH_GOALS | blood pressure, bone density, physiotherapy |

---

## 📁 Project Structure

```
fitbuddy-ai/
├── app.py                       # Flask app — routes, API endpoints, startup
├── requirements.txt             # Python dependencies
├── app.json                     # IBM Cloud / Heroku deployment config
├── .env                         # Runtime credentials (git-ignored)
├── .env.example                 # Credential template (safe to commit)
├── README.md
│
├── services/
│   ├── __init__.py
│   ├── orchestrate.py           # IBM watsonx integration (3-layer fallback)
│   └── topic_filter.py          # Server-side fitness topic guard
│
├── static/
│   ├── css/
│   │   └── style.css            # Green/white theme, glassmorphism, animations
│   ├── js/
│   │   ├── main.js              # Global JS — nav scroll, animations, toasts
│   │   └── chat.js              # AI Chat page logic, source badge display
│   └── images/
│       └── favicon.svg          # SVG favicon (green heart-pulse icon)
│
└── templates/
    ├── base.html                # Base layout — sticky nav, offcanvas, footer
    ├── index.html               # Home — hero, features, benefits, CTA
    ├── chat.html                # AI Chat — ChatGPT-style UI, sidebar prompts
    ├── workout.html             # Workout Planner — 7-day schedule generator
    ├── nutrition.html           # Nutrition — diet selector, 4 meal categories
    ├── bmi.html                 # BMI Calculator — animated gauge
    ├── calories.html            # Calorie Calculator — BMR/TDEE/macros
    ├── water.html               # Water Tracker — animated glass, schedule
    ├── dashboard.html           # Progress Dashboard — 5 Chart.js charts
    ├── motivation.html          # Motivation — quotes, tips, challenges
    ├── about.html               # About — IBM watsonx & Cloud Lite
    └── contact.html             # Contact — form + FAQ accordion
```

---

## 🌐 REST API Reference

| Endpoint | Method | Input | Output |
|---|---|---|---|
| `/api/chat` | POST | `{ message }` | `{ response, source, restricted?, timestamp }` |
| `/api/chat/clear` | POST | — | `{ status: "cleared" }` |
| `/api/health` | GET | — | `{ status, ai: { orchestrate, watsonx_ai, fallback } }` |
| `/api/workout` | POST | `{ goal, level, duration }` | `{ plan: [7 days] }` |
| `/api/nutrition` | POST | `{ diet }` | `{ plan: { breakfast, lunch, dinner, snacks } }` |
| `/api/bmi` | POST | `{ height, weight }` | `{ bmi, category, suggestion, color }` |
| `/api/calories` | POST | `{ age, gender, height, weight, activity }` | `{ bmr, tdee, weight_loss, weight_gain }` |
| `/api/water` | POST | `{ weight, activity, climate }` | `{ ml, liters, glasses }` |
| `/api/contact` | POST | `{ name, email, subject, message }` | `{ status, message }` |
| `/api/motivation/refresh` | GET | — | `{ quote, tip, habit, challenge }` |

### `/api/chat` Response Shape

```json
{
  "response":  "Start with bodyweight squats, push-ups, and lunges...",
  "source":    "watsonx_ai",
  "timestamp": "21:05"
}
```

When a non-fitness message is blocked by the topic filter:

```json
{
  "success":    true,
  "restricted": true,
  "response":   "I'm FitBuddy AI, a fitness and wellness assistant...",
  "source":     "topic_filter",
  "timestamp":  "21:05"
}
```

---

## 🚀 Deploy to IBM Cloud

```bash
# Log in and target Cloud Foundry
ibmcloud login --sso
ibmcloud target --cf

# Push the app (uses app.json for configuration)
ibmcloud cf push fitbuddy-ai

# Set environment variables in IBM Cloud
ibmcloud cf set-env fitbuddy-ai SECRET_KEY your-secret
ibmcloud cf set-env fitbuddy-ai ORCHESTRATE_API_KEY your-key
ibmcloud cf set-env fitbuddy-ai ORCHESTRATE_AGENT_ID ebea739a-784d-43d1-a90b-5b06d8591404
ibmcloud cf set-env fitbuddy-ai IBM_CLOUD_API_KEY your-ibm-key
ibmcloud cf set-env fitbuddy-ai WATSONX_PROJECT_ID your-project-id
ibmcloud cf restage fitbuddy-ai
```

---

## 🔒 Security

- All credentials loaded via `python-dotenv` from `.env` — never hardcoded
- `.env` is git-ignored; `.env.example` is the only file safe to commit
- Topic filter blocks all non-fitness requests before any AI call
- Session history capped at 20 turns; cleared on explicit request
- Input validated and length-limited (max 2000 chars) before processing

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

*Built with IBM watsonx Orchestrate, IBM watsonx.ai, and IBM Cloud Lite*
