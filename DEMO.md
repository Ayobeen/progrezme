# The five-minute Comeback demonstration

Open http://127.0.0.1:8001. The local demo users are `educator`, `tunde`, and `amina`; use the password printed by `seed_scenarios` when creating them. Use separate browser profiles or log out between roles.

## 1. Introduce the problem (30 seconds)

“Two learners appear to be falling behind. The same reminder will not solve both problems. Progrez combines evidence with learner confirmation, then gives the educator a different intervention to approve.”

Log in as **educator**. Show Tunde's recent low scores and Amina's high scores alongside three missed planned sessions. These are fictional seeded histories, labelled as demo scenarios in this guide.

## 2. Listen to each learner (one minute)

- **Tunde:** open the Comeback check-in and choose **Difficult concepts**. Note: “I mix up the input parameter and the returned answer.” A draft may already be pending from local verification.
- **Amina:** choose **Not enough time**. Note: “I understand the lessons, but can only fit in ten minutes at a time.”

Neither learner name is used by the engine. The recorded target lesson, confirmed challenge and time budget determine the rule draft. AI personalization is optional and its source is shown honestly.

## 3. Keep the educator in control (one minute)

Log in as **educator**. Review both interventions.

- Tunde gets a simpler explanation of function parameters and returns, a traced example, and independent practice.
- Amina gets three ten-minute missions focused on Data Types.

Edit a mission or add guidance. Click **Approve & assign**. Show that the assignment records the educator and approval time.

## 4. Demonstrate learning (two minutes)

Log in as **tunde** and open the plan. Record honest demo practice for the three missions, in order:

1. “The parameter receives the input. Return sends the calculated result back to the caller.”
2. “double(3) receives 3, calculates 3 times 2, and returns 6 to answer.”
3. “Changing the call to double(5) returns 10; the definition stays the same.”

Take the recovery competency check. Presenter answer key: **5**, **return result**, **6**. The score changes from 33% to 100%; completed lessons increase from 7 to 8. Functions is now earned and Applied Python unlocks.

For **amina**, record the data-type idea, an example and its explanation across the missions. Presenter answer key: **18**, **String**, **True**. Her completed lessons increase from 2 to 3. There was no prior attempt on Data Types, so the UI shows no fabricated baseline; it records a new competency and resumed learning instead. Getting Started is now earned.

The suite also verifies that failed, stale and unrelated assessments cannot count as successful recovery.

## 5. Celebrate a verified achievement (30 seconds)

On the learner journey, select the newly earned milestone under **Progrez Circle**, then enable its private link. Open the link in another browser and send a preset encouragement. Show that scores, check-in notes and recovery challenges are absent. Disable sharing to revoke the URL.

Close with: “Progrez doesn't just ask learners to come back. It helps educators respond to the reason they left—and checks whether they're making progress again.”

## Repeatability

The seed commands preserve existing users and histories. They do not reset completed scenarios. For a fresh isolated rehearsal, use a separate copy of this project without its SQLite database, run migrations and `seed_scenarios`, and use the password printed by that command. Keep the original local database intact.
