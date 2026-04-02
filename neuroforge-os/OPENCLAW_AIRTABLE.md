# OpenClaw × Airtable Integration

Continuously logs OpenClaw agent interactions to Airtable for self-improvement and analytics.

## Tables Created

1. **OpenClaw Interactions** — Every agent interaction
   - User Query, Response, Search Used, Response Time, Satisfaction, Timestamp, Tags

2. **Telegram Messages** — All Telegram bot activity
   - User ID, Message, Bot Response, Success, Error Log, Timestamp

3. **Lead Tracking** — Music business prospects
   - Contact Name, Telegram ID, Interaction Count, Interest Level, Status, Notes

4. **Agent Performance** — Performance metrics over time
   - Metric, Value, Date, Category, Notes

5. **Improvement Suggestions** — Auto-generated improvements
   - Issue, Suggested Fix, Priority, Status, Implementation, Dates

6. **Model Optimization Log** — Prompt version history
   - Prompt Version, Change Description, Date Changed, Status

## Setup

### 1. Environment Variables (already in .env)
```
AIRTABLE_API_KEY=AIRTABLE_API_TOKEN
AIRTABLE_BASE_ID=applXEAjh6k3Xmybl
```

### 2. Use the Logger in Your Code

```python
from scripts.openclaw_airtable_logger import OpenClawAirtableLogger

logger = OpenClawAirtableLogger()

# Log an interaction
logger.log_interaction(
    user_query="What's trending in music marketing?",
    response="Here are the top trends...",
    search_used="Brave Search",
    satisfaction="High",
    tags="music,marketing"
)

# Log Telegram activity
logger.log_telegram_message(
    user_id="8318047312",
    message="What should I do with my new track?",
    bot_response="Here are 5 distribution strategies...",
    success=True
)

# Log a lead
logger.log_lead(
    name="John Doe",
    telegram_id="123456789",
    interest_level="High",
    status="Active"
)

# Suggest an improvement
logger.suggest_improvement(
    issue="Bot response is too generic for music queries",
    suggested_fix="Add genre-specific recommendations based on user history",
    priority="High"
)

# Log a model optimization
logger.log_optimization(
    prompt_version="v1.2",
    description="Added music industry context, improved response relevance",
    status="Testing"
)
```

### 3. Get Analytics

```python
# Get low-performing queries
low_perf = logger.get_low_performance_queries()

# Get pending improvements
pending = logger.get_pending_improvements()
```

## Self-Improvement Loop

The agent improves continuously:

1. **Log interactions** → Airtable stores every query/response
2. **User feedback** → Track satisfaction scores
3. **Analyze performance** → Identify low-performing queries
4. **Generate suggestions** → Auto-suggest prompt improvements
5. **Implement & test** → Update prompts and log new versions
6. **Repeat** → System learns from patterns

## Usage

### Log from your OpenClaw agent
```python
# In your OpenClaw handler
logger.log_interaction(
    user_query=user_input,
    response=agent_response,
    search_used="web",
    satisfaction=get_user_rating()  # 1-5
)
```

### Docker service (optional)
```bash
docker compose run --rm openclaw-logger
```

### Direct Python
```bash
python3 scripts/openclaw_airtable_logger.py
```

## Airtable Base

Base ID: `applXEAjh6k3Xmybl`

View your data at: https://airtable.com/applXEAjh6k3Xmybl

## Next Steps

1. **Integrate into OpenClaw** — Import logger in your agent handler
2. **Add Telegram logging** — Hook into bot message events
3. **Create dashboards** — Use Airtable views to track KPIs
4. **Auto-improve prompts** — Use Claude to read suggestions and update system prompts
5. **Schedule optimization** — Run weekly prompt updates based on patterns
