# Progrez Comeback

An educator-facing learning recovery assistant with a lightweight learner portal.

**One Python course. Three confirmed challenges. A recovery engine that measures progress.**

## Run locally (Windows)

Python 3.12+ is required. This workspace already has dependencies installed in `.venv`.

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001
```

Open [the local app](http://127.0.0.1:8001). Port 8001 avoids the separate application already using 8000 on this machine.

For a fresh checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_scenarios
```

`seed_scenarios` creates fictional `tunde`, `amina`, and `educator` accounts and prints a generated local password. It preserves existing users and histories. `--password` can set the password for newly created demo accounts. Do not seed demo users on a public deployment.

Use the password printed by `seed_scenarios` for the newly created demo accounts. Each learner starts with a fictional history and can confirm their challenge through a Comeback check-in.

| Account | Portal | Initial scenario |
| --- | --- | --- |
| tunde | Learner | 7 completed lessons; two 33% attempts on Parameters and Returns; four days inactive |
| amina | Learner | 2 completed lessons at 100%; three missed scheduled sessions; six days inactive |
| educator | Educator | Reviews, edits, approves and assigns recovery drafts |

These passwords are only for the local fictional demonstration. Create a separate administrator with `manage.py createsuperuser`. Staff accounts access the educator portal; self-registration creates ordinary learners only. All educators can see all learners in this single-class MVP.

## What works

- Four gated milestones and eleven Python lessons with worked examples.
- Three regular questions and three distinct reassessment questions per lesson.
- Persisted lesson visits, quiz attempts, competency completion, scheduled sessions and mission activity.
- Risk flags for inactivity, repeated difficulty, missed planned sessions and a week-over-week drop in recorded activity.
- Learner-confirmed time, difficulty or motivation challenges. Signals never automatically establish a diagnosis.
- One active recovery plan per journey, targeted to the next unfinished unlocked lesson.
- Exactly three editable recovery missions. Rules choose the approach; optional AI personalizes the text.
- Educator draft saving, approval and assignment, closure, evidence review and outcome inspection.
- Ordered learner missions with saved practice/reflections, followed by a dedicated assessment.
- Milestone sharing is opt-in, restricted to earned milestones, and revocable. Revocation invalidates the old token permanently.
- One-click preset encouragement, limited to one per browser session per link.

## Recovery evidence

The baseline is the most recent **quiz score on the target lesson**, not the momentum indicator. A missing baseline is shown as unknown.

Recovery requires:

1. Educator approval.
2. All three missions recorded after assignment.
3. A new assessment associated with this plan and its target lesson, after the missions.
4. At least 70% on that assessment.
5. At least a 20-percentage-point improvement over the target baseline **or** an increase in demonstrated lesson competencies.

A failed, old, unrelated, ordinary lesson quiz or a completion click cannot mark recovery successful. A learner with no target baseline is evaluated on a new competency and resumed learning, with no invented before score. Assessment results and course progress are shown separately.

This is a hackathon evidence rule, not a validated causal measure of intervention effectiveness. Three multiple-choice questions and self-reported practice cannot establish long-term mastery. Reassessment questions differ from the initial quiz but are reused on retries.

## AI personalization (optional)

The app works without any external API call. Without a key, drafts are visibly labelled **rule-based**.

To enable OpenAI personalization, set environment variables in the shell that launches Django:

```powershell
$env:OPENAI_API_KEY = 'your-key'
$env:OPENAI_MODEL = 'gpt-4o-mini'
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001
```

Restart the server after changing configuration. Do not paste keys into chat or commit them. This project reads environment variables; it does not automatically load a `.env` file.

The adapter uses the [Responses API with Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses), `store: false`, a 20-second timeout, and local validation of exactly three bounded missions. It sends the confirmed challenge, available time, lesson content, aggregate learning signals and rule draft (which can include the learning goal). It does not send usernames, passwords, learner notes, or raw answer text. Educators see the source and fallback reason.

Network errors, refusal, incomplete output and malformed responses fall back to the rule draft. AI does not approve plans, alter quiz grading, or decide recovery. Live AI has not been exercised in this workspace; adapter success and failure paths are covered with mocked API responses.

## Judge demonstration

See [DEMO.md](DEMO.md) for a five-minute walkthrough.

1. Open the educator overview and compare Tunde's repeated failures with Amina's high scores and missed sessions.
2. As Tunde, confirm **Difficult concepts**. As Amina, confirm **Not enough time**.
3. As educator, inspect the evidence and modify a mission or guidance. Approve each plan.
4. Complete each learner's missions and target reassessment.
5. Show Tunde's score improvement and Amina's newly demonstrated competency.
6. Share a newly earned milestone and send encouragement through its private link.

## Verification

```powershell
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Tests cover the two scenarios, permissions and ownership, draft editing/approval, duplicate prevention, ordered mission work, failed/stale/unrelated assessments, milestone gating, private achievement sharing, link revocation, session scheduling, AI response validation/fallback, and repeatable seeding.

## Database upgrade

The original prototype created tables through `migrate --run-syncdb`. The workspace now has versioned migrations. Its original database was backed up to `db.before-comeback.sqlite3` before applying the changes.

For another existing prototype database, back it up, then use:

```powershell
.\.venv\Scripts\python.exe manage.py migrate --fake-initial
```

The initial migration adopts existing tables. The second adds recovery evidence and session tables. Old plans are preserved as closed legacy records because their momentum baseline was not a comparable quiz score. Old sharing is disabled until a verified milestone is selected.

## Deployment boundary

This deliverable runs locally; it has not been published. For a hosted pilot, use a production WSGI server and static-file service, set `DJANGO_DEBUG=0`, a strong `DJANGO_SECRET_KEY`, exact `DJANGO_ALLOWED_HOSTS`, HTTPS and secure cookies. SQLite is appropriate for this local demo; a multi-user pilot should use PostgreSQL and stronger login/encouragement rate limits.

The scheduled-session UI uses UTC explicitly. A quiz on the scheduled UTC date marks attendance; a visit alone does not. There are no background reminder jobs, external LMS integrations, PDF ingestion, marketplace, password-reset emails, or cohort-specific educator assignments in this focused MVP.
