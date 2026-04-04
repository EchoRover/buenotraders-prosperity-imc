# Two-Claude Coordination

## File Ownership

**Claude 1 (this agent) owns:**
- `models/e1_v*.py` — production series
- `models/e1_p*.py` — probe series

**Claude 2 (other agent) owns:**
- `models/e1_crazy*.py` — crazy series

**SHARED (both can read AND write):**
- `docs/changelog.md` — both APPEND new entries (don't modify each other's)
- `docs/strategy-log.md` — both APPEND
- `docs/research-notes.md` — both APPEND
- `models/REGISTRY.md` — both APPEND rows (don't modify each other's rows)
- `scripts/`
- `logs/`
- `CLAUDE.md`
- `COORDINATION.md`

## Communication Protocol

1. **Communicate through shared docs** — both read AND write to changelog, strategy-log, research-notes, REGISTRY
2. **When you discover something**, write it to `docs/research-notes.md` so the other claude sees it
3. **When submitting a model**, add a row to REGISTRY.md with results
4. **When analyzing logs**, write findings to shared docs so both benefit
5. **Model naming**: v-series = claude1, crazy-series = claude2. No overlap.
6. **NEVER modify the other claude's model files**
7. **READ the shared docs before building** — the other claude may have already found something relevant

## Current Best Components
- EMERALDS best: crazy1 = 1,050 (zero skew + limit=80)
- TOMATOES best: v10 = 1,477 (filtered mid + reversion)
- Combined target: 2,527+ → push TOMATOES to 1,950+ for 3,000

## Log Processing
- **Inbox folder:** `evan/inbox/` — drop zip files here
- **Script:** `python3 evan/scripts/process_inbox.py` — auto-extracts, identifies model + ID, moves to userdatadump, prints scores
- **After parsing:** write detailed analysis to `docs/research-notes.md` (format in CHAT.md)

## Key Findings (shared knowledge)
- Backtester overestimates 10-20x, don't optimize for it
- Position limit is 80 (probe confirmed)
- EMERALD sim is deterministic — same code = same fills
- Filtered mid (vol>=15) + reversion(-0.229) is the TOMATOES breakthrough
- Zero skew + limit=80 is the EMERALDS breakthrough
- Penny-jump on TOMATOES FAILS (Lakshan v3 proved this)
- A-S dynamic spread FAILS live (v11 proved this)
- **limit=80 on TOMATOES FAILS** (crazy2: T dropped 1,477→743). Limit=80 only works on STABLE products.
- **DO NOT change TOMATOES limit from 50.** Keep hard_limit=40.
