from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .models import Attempt, Lesson, LearningEvent, RecoveryPlan, RecoveryMission

PLANS = {
    'TIME': 'Break the next lesson into three short missions that fit the learner’s available time.',
    'DIFFICULTY': 'Provide a simpler explanation, a worked example and guided practice on the difficult concept.',
    'MOTIVATION': 'Connect the next lesson to a personal goal and build confidence with a small, visible win.',
}

def momentum(journey):
    progress = list(journey.progress.all())
    total = Lesson.objects.filter(milestone__course=journey.course).count()
    completion = sum(p.completed for p in progress) / max(total, 1)
    scores = [p.best_score for p in progress if p.attempts]
    performance = sum(scores) / max(len(scores), 1) / 100
    consistency = max(0, 1 - (timezone.now() - journey.last_active_at).days / 14)
    return round(100 * (.35 * completion + .4 * performance + .25 * consistency))

def signals(journey):
    now = timezone.now()
    attempts = list(Attempt.objects.filter(journey=journey).order_by('-created_at', '-id')[:10])
    return {
        'days_inactive': max(0, (now - journey.last_active_at).days),
        'missed_sessions': journey.sessions.filter(scheduled_for__date__lt=timezone.localdate(now), completed_at__isnull=True).count(),
        'repeated_difficulties': journey.progress.filter(attempts__gte=2, completed=False).count(),
        'recent_scores': [a.score for a in reversed(attempts)],
        'completed_lessons': journey.progress.filter(completed=True).count(),
        'recent_activity': journey.events.filter(created_at__gte=now - timedelta(days=7)).count(),
        'previous_activity': journey.events.filter(created_at__gte=now - timedelta(days=14), created_at__lt=now - timedelta(days=7)).count(),
    }

def risk_reasons(journey):
    s = signals(journey)
    reasons = []
    if s['days_inactive'] >= 3:
        reasons.append(f"No recorded learning activity for {s['days_inactive']} days")
    if s['missed_sessions']:
        reasons.append(f"{s['missed_sessions']} planned session(s) missed")
    if s['repeated_difficulties']:
        reasons.append(f"{s['repeated_difficulties']} lesson(s) with repeated unsuccessful quiz attempts")
    if s['previous_activity'] >= 3 and s['recent_activity'] < s['previous_activity'] / 2:
        reasons.append('Recorded activity fell by more than half compared with the previous week')
    return reasons

def milestones_for(journey):
    completed = set(journey.progress.filter(completed=True).values_list('lesson_id', flat=True))
    milestones = list(journey.course.milestones.prefetch_related('lessons'))
    unlocked = True
    progress = {p.lesson_id: p for p in journey.progress.all()}
    for milestone in milestones:
        lessons = list(milestone.lessons.all())
        milestone.unlocked = unlocked
        milestone.earned = bool(lessons) and all(l.pk in completed for l in lessons)
        milestone.items = [{'lesson': l, 'progress': progress.get(l.pk)} for l in lessons]
        milestone.done_count = sum(l.pk in completed for l in lessons)
        unlocked = unlocked and milestone.earned
    return milestones

def lesson_unlocked(journey, lesson):
    return any(m.pk == lesson.milestone_id and m.unlocked for m in milestones_for(journey))

def target_lesson(journey):
    for milestone in milestones_for(journey):
        if milestone.unlocked:
            for item in milestone.items:
                if not item['progress'] or not item['progress'].completed:
                    return item['lesson']
    return None

def record_activity(journey, kind, lesson=None):
    now = timezone.now()
    LearningEvent.objects.create(journey=journey, kind=kind, lesson=lesson)
    journey.last_active_at = now
    journey.save(update_fields=['last_active_at'])
    if kind == 'QUIZ':
        journey.sessions.filter(scheduled_for__date=timezone.localdate(now), completed_at__isnull=True).update(completed_at=now)

def rule_missions(checkin, lesson):
    minutes = max(5, min(checkin.journey.daily_minutes, 15))
    content = lesson.content
    if checkin.reason == 'DIFFICULTY':
        titles = ['Make the concept click', 'Trace a worked example', 'Practice without the example']
        instructions = [
            f'Read this explanation of {lesson.title}:\n\n{content}\n\nIn your own words, explain the main idea and name the part you found confusing.',
            f'Use the example in “{lesson.title}”. Write down what each line does. Predict its result before checking the explanation. Record your prediction and what you learned.',
            f'Create a small variation of the example for {lesson.title}. Change a value or input and explain how the result changes. Record your work, then take the new competency check below.',
        ]
    elif checkin.reason == 'TIME':
        titles = ['One idea, one short session', 'A small practice mission', 'Explain it and check your progress']
        instructions = [
            f'Set aside {minutes} minutes for {lesson.title}. Read only this short section:\n\n{content}\n\nRecord the one idea you want to remember.',
            f'In another {minutes}-minute slot, write your own example of {lesson.title}. Predict what happens. Record the example and your prediction.',
            f'Use your final {minutes}-minute slot to explain the example without looking back. Record your explanation, then complete the short competency check below. Schedule your next manageable session.',
        ]
    else:
        goal = checkin.journey.learning_goal or 'build something useful with Python'
        titles = ['Reconnect with your goal', 'Make one small thing work', 'Recognize your next step']
        instructions = [
            f'Your goal: {goal}. Read this idea from {lesson.title}:\n\n{content}\n\nDescribe one way this idea could help your goal.',
            f'Create the smallest example you can using {lesson.title}. You only need one working idea. Write your example and explain what it does.',
            'Record what you can do now that you could not do before. Choose one next learning session, then demonstrate this skill in the competency check below.',
        ]
    return [dict(title=t, instructions=i, minutes=minutes) for t, i in zip(titles, instructions)]

@transaction.atomic
def create_recovery(checkin, use_ai=True):
    existing = RecoveryPlan.objects.filter(journey=checkin.journey, status__in=['PENDING', 'APPROVED']).first()
    if existing:
        return existing
    lesson = target_lesson(checkin.journey)
    if not lesson:
        raise ValueError('You have completed this course. There is no unfinished lesson to recover.')
    latest = Attempt.objects.filter(journey=checkin.journey, lesson=lesson).order_by('-created_at', '-id').first()
    evidence = signals(checkin.journey)
    recommendation = PLANS[checkin.reason]
    missions = rule_missions(checkin, lesson)
    source, note = 'RULES', 'Rule-based draft; AI personalization is not configured.'
    if use_ai:
        from .ai import personalize
        result, note = personalize(checkin, lesson, evidence, missions)
        if result:
            recommendation, missions, source = result['recommendation'], result['missions'], 'AI'
    plan = RecoveryPlan.objects.create(
        journey=checkin.journey, checkin=checkin, target_lesson=lesson,
        recommended_action=recommendation,
        step_one=missions[0]['title'], step_two=missions[1]['title'], step_three=missions[2]['title'],
        baseline_score=latest.score if latest else None,
        baseline_completed=evidence['completed_lessons'], evidence=evidence,
        generation_source=source, generation_note=note,
    )
    for order, mission in enumerate(missions, 1):
        RecoveryMission.objects.create(plan=plan, order=order, **mission)
    return plan

def evaluate_recovery(plan, attempt):
    if plan.status != 'APPROVED' or not plan.approved_at:
        return False
    missions = list(plan.missions.all())
    if len(missions) != 3 or any(not m.completed_at for m in missions):
        return False
    if (attempt.recovery_plan_id != plan.pk or attempt.journey_id != plan.journey_id
            or attempt.lesson_id != plan.target_lesson_id
            or attempt.created_at <= max([plan.approved_at] + [m.completed_at for m in missions])):
        return False
    plan.followup_score = attempt.score
    progress = plan.journey.progress.filter(completed=True).count()
    plan.evidence = {**plan.evidence, 'followup_completed': progress}
    gained = progress > plan.baseline_completed
    improved = plan.baseline_score is not None and attempt.score >= plan.baseline_score + 20
    successful = attempt.score >= 70 and (improved or gained)
    if successful:
        plan.status = 'COMPLETED'
        plan.completed_at = attempt.created_at
        plan.outcome = f'Target competency demonstrated at {attempt.score}%. Completed lessons: {plan.baseline_completed} → {progress}. Learning resumed through three missions and a new assessment.'
    else:
        plan.outcome = f'Follow-up score: {attempt.score}%. Recovery is not yet evidenced. Review the lesson and retry; a pass of at least 70% plus score improvement or new lesson progress is required.'
    plan.save(update_fields=['followup_score', 'status', 'completed_at', 'outcome', 'evidence'])
    return successful


def recovery_progress_count(plan):
    # Do not attribute subsequent learning to a historical reassessment.
    # Older plans without a snapshot are shown as unknown, never reconstructed.
    if plan.followup_score is not None:
        return plan.evidence.get('followup_completed')
    return plan.journey.progress.filter(completed=True).count()
