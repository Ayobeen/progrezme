import secrets
from functools import wraps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import Course, Journey, Lesson, LessonProgress, Attempt, CheckIn, RecoveryPlan, Encouragement
from .forms import ReviewForm, MissionFormSet, SessionForm, PreferencesForm
from .services import (momentum, risk_reasons, signals, create_recovery, milestones_for,
    lesson_unlocked, target_lesson, record_activity, evaluate_recovery, recovery_progress_count)


def request_id(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise Http404('Invalid identifier')
    if not 0 < number <= 9223372036854775807:
        raise Http404('Invalid identifier')
    return number


def educator_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            return HttpResponseForbidden('Educator access is required.')
        return view(request, *args, **kwargs)
    return wrapped


def home(request):
    return render(request, 'core/home.html', {'courses': Course.objects.all()})


def register(request):
    form = UserCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect('dashboard')
    return render(request, 'core/form.html', {'form': form, 'title': 'Your next chapter starts here', 'button': 'Create learner account'})


@login_required
def dashboard(request):
    if request.user.is_staff:
        return redirect('educator')
    journeys = list(Journey.objects.filter(learner=request.user).select_related('course'))
    for j in journeys:
        j.momentum = momentum(j)
        j.risks = risk_reasons(j)
        j.completed_count = j.progress.filter(completed=True).count()
        j.active_plan = j.recovery_plans.filter(status__in=['PENDING', 'APPROVED']).first()
    return render(request, 'core/dashboard.html', {'journeys': journeys, 'courses': Course.objects.exclude(pk__in=[j.course_id for j in journeys])})


@login_required
@require_POST
def start(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    journey, _ = Journey.objects.get_or_create(learner=request.user, course=course)
    return redirect('journey', pk=journey.pk)


@login_required
def journey_detail(request, pk):
    journey = get_object_or_404(Journey, pk=pk, learner=request.user)
    session_form, preferences = SessionForm(), PreferencesForm(instance=journey)
    if request.method == 'POST':
        if request.POST.get('action') == 'schedule':
            session_form = SessionForm(request.POST)
            if session_form.is_valid():
                journey.sessions.get_or_create(scheduled_for=session_form.cleaned_data['scheduled_for'])
                messages.success(request, 'Your next learning session is scheduled.')
                return redirect('journey', pk=pk)
        elif request.POST.get('action') == 'preferences':
            preferences = PreferencesForm(request.POST, instance=journey)
            if preferences.is_valid():
                preferences.save()
                messages.success(request, 'Your learning preferences are saved.')
                return redirect('journey', pk=pk)
    milestones = milestones_for(journey)
    return render(request, 'core/journey.html', {
        'journey': journey, 'milestones': milestones, 'earned': [m for m in milestones if m.earned],
        'momentum': momentum(journey), 'risks': risk_reasons(journey), 'signals': signals(journey),
        'plans': journey.recovery_plans.order_by('-created_at')[:5], 'next_lesson': target_lesson(journey),
        'session_form': session_form, 'preferences': preferences, 'now': timezone.now(),
        'sessions': journey.sessions.order_by('-scheduled_for')[:5],
        'encouragements': journey.encouragements.order_by('-created_at')[:5],
    })


@login_required
def lesson_detail(request, pk):
    journey = get_object_or_404(Journey, pk=request_id(request.GET.get('journey') or request.POST.get('journey')), learner=request.user)
    lesson = get_object_or_404(Lesson, pk=pk, milestone__course=journey.course)
    if not lesson_unlocked(journey, lesson):
        messages.info(request, 'Demonstrate the previous milestone’s competencies to unlock this lesson.')
        return redirect('journey', pk=journey.pk)
    plan = None
    plan_id = request.GET.get('plan') or request.POST.get('plan')
    if plan_id:
        plan = get_object_or_404(RecoveryPlan, pk=request_id(plan_id), journey=journey, target_lesson=lesson, status='APPROVED')
        if plan.missions.count() != 3 or plan.missions.filter(completed_at__isnull=True).exists():
            messages.error(request, 'Complete the three assigned missions before reassessment.')
            return redirect('recovery', pk=plan.pk)
    questions = list(lesson.questions.filter(is_followup=bool(plan)))
    result = None
    if request.method == 'POST':
        answers = [request.POST.get(f'q_{q.pk}') for q in questions]
        if not questions:
            messages.error(request, 'This assessment is not available yet. Please contact your educator.')
        elif any(a not in ('A', 'B', 'C') for a in answers):
            messages.error(request, 'Please answer every question.')
        else:
            score = round(100 * sum(a == q.correct for a, q in zip(answers, questions)) / len(questions))
            with transaction.atomic():
                if plan:
                    plan = RecoveryPlan.objects.select_for_update().get(pk=plan.pk)
                    if plan.status != 'APPROVED':
                        return redirect('recovery', pk=plan.pk)
                progress, _ = LessonProgress.objects.select_for_update().get_or_create(journey=journey, lesson=lesson)
                progress.attempts += 1
                progress.best_score = max(score, progress.best_score)
                if score >= 70:
                    progress.completed = True
                progress.save()
                attempt = Attempt.objects.create(journey=journey, lesson=lesson, score=score, recovery_plan=plan)
                record_activity(journey, 'QUIZ', lesson)
                if plan:
                    recovered = evaluate_recovery(plan, attempt)
                    messages.success(request, 'Recovery evidenced. You have made measurable progress!') if recovered else messages.info(request, 'Not yet. Review the feedback and try the competency check again.')
                    return redirect('recovery', pk=plan.pk)
            request.session[f'lesson_result_{journey.pk}_{lesson.pk}'] = score
            return redirect(f'{request.path}?journey={journey.pk}')
    else:
        result = request.session.pop(f'lesson_result_{journey.pk}_{lesson.pk}', None)
        # A refresh within the same day is not a new engagement event.
        if not journey.events.filter(kind='LESSON', lesson=lesson, created_at__date=timezone.localdate()).exists():
            record_activity(journey, 'LESSON', lesson)
    active_plan = journey.recovery_plans.filter(status__in=['PENDING', 'APPROVED']).first()
    return render(request, 'core/lesson.html', {'journey': journey, 'lesson': lesson, 'questions': questions, 'result': result, 'plan': plan, 'active_plan': active_plan})


@login_required
def checkin(request, pk):
    journey = get_object_or_404(Journey, pk=pk, learner=request.user)
    existing = journey.recovery_plans.filter(status__in=['PENDING', 'APPROVED']).first()
    if existing:
        return redirect('recovery', pk=existing.pk)
    if request.method == 'POST':
        reason = request.POST.get('reason')
        if reason not in dict(CheckIn.REASONS):
            messages.error(request, 'Choose time, difficulty or motivation.')
        elif not target_lesson(journey):
            messages.info(request, 'You have demonstrated every lesson in this course. Well done!')
            return redirect('journey', pk=pk)
        else:
            with transaction.atomic():
                Journey.objects.select_for_update().get(pk=pk)
                existing = journey.recovery_plans.filter(status__in=['PENDING', 'APPROVED']).first()
                if existing:
                    return redirect('recovery', pk=existing.pk)
                check = CheckIn.objects.create(journey=journey, reason=reason, note=request.POST.get('note', '')[:1000])
                plan = create_recovery(check)
            return redirect('recovery', pk=plan.pk)
    return render(request, 'core/checkin.html', {'journey': journey, 'reasons': CheckIn.REASONS, 'risks': risk_reasons(journey)})


@login_required
def recovery(request, pk):
    plan = get_object_or_404(RecoveryPlan.objects.select_related('journey', 'target_lesson', 'checkin'), pk=pk, journey__learner=request.user)
    if request.method == 'POST':
        with transaction.atomic():
            plan = RecoveryPlan.objects.select_for_update().get(pk=pk)
            if plan.status != 'APPROVED':
                messages.error(request, 'Missions must be assigned by an educator before you begin.')
            elif request.POST.get('action') == 'mission':
                mission = get_object_or_404(plan.missions, pk=request_id(request.POST.get('mission')))
                reflection = request.POST.get('reflection', '').strip()
                if plan.missions.filter(order__lt=mission.order, completed_at__isnull=True).exists():
                    messages.error(request, 'Complete the previous mission first.')
                elif len(reflection) < 15 or len(reflection) > 3000:
                    messages.error(request, 'Record your practice or reflection in 15–3,000 characters.')
                elif not mission.completed_at:
                    mission.reflection = reflection
                    mission.completed_at = timezone.now()
                    mission.save(update_fields=['reflection', 'completed_at'])
                    record_activity(plan.journey, 'MISSION', plan.target_lesson)
                    messages.success(request, 'Mission recorded. Your competency check will provide evidence of progress.')
            else:
                messages.info(request, 'Recovery is evaluated automatically from the target competency check, not a completion button.')
        return redirect('recovery', pk=pk)
    missions = list(plan.missions.all())
    ready = len(missions) == 3 and all(m.completed_at for m in missions)
    return render(request, 'core/recovery.html', {'plan': plan, 'missions': missions, 'ready': ready, 'completed_count': recovery_progress_count(plan)})


@educator_required
def educator(request):
    journeys = list(Journey.objects.select_related('learner', 'course').order_by('learner__username'))
    for j in journeys:
        j.signals = signals(j)
        j.risks = risk_reasons(j)
        j.latest_plan = j.recovery_plans.select_related('checkin').order_by('-created_at').first()
    return render(request, 'core/educator.html', {
        'journeys': journeys, 'at_risk': sum(bool(j.risks) for j in journeys),
        'pending': RecoveryPlan.objects.filter(status='PENDING').count(),
        'recovered': RecoveryPlan.objects.filter(status='COMPLETED').count(),
        'plans': RecoveryPlan.objects.select_related('journey__learner', 'checkin', 'target_lesson').order_by('status', '-created_at'),
        'ai_configured': bool(settings.OPENAI_API_KEY),
    })


@educator_required
def educator_learner(request, pk):
    journey = get_object_or_404(Journey.objects.select_related('learner', 'course'), pk=pk)
    return render(request, 'core/educator_learner.html', {
        'journey': journey, 'signals': signals(journey), 'risks': risk_reasons(journey),
        'milestones': milestones_for(journey), 'plans': journey.recovery_plans.order_by('-created_at'),
        'attempts': Attempt.objects.filter(journey=journey).select_related('lesson').order_by('-created_at')[:20],
        'sessions': journey.sessions.all(), 'now': timezone.now(),
    })


@educator_required
def review(request, pk):
    with transaction.atomic():
        plan = get_object_or_404(RecoveryPlan.objects.select_for_update().select_related('journey__learner', 'checkin', 'target_lesson'), pk=pk)
        form = ReviewForm(request.POST or None, instance=plan)
        formset = MissionFormSet(request.POST or None, instance=plan)
        if request.method == 'POST':
            if plan.status != 'PENDING':
                messages.error(request, 'This plan has already been reviewed. Assigned evidence cannot be rewritten.')
                return redirect('review', pk=pk)
            action = request.POST.get('action')
            if action == 'close':
                plan.status = 'CANCELLED'
                plan.reviewed_by = request.user
                plan.admin_feedback = request.POST.get('admin_feedback', '')[:3000]
                plan.save(update_fields=['status', 'reviewed_by', 'admin_feedback'])
                messages.success(request, 'Draft closed. The learner can submit a new check-in.')
                return redirect('educator')
            valid_form, valid_missions = form.is_valid(), formset.is_valid()
            if valid_form and valid_missions and action in ('save', 'approve'):
                plan = form.save(commit=False)
                if action == 'approve':
                    if not plan.target_lesson or not plan.target_lesson.questions.filter(is_followup=True).exists():
                        messages.error(request, 'Add a follow-up assessment to this lesson before assigning a plan.')
                        return redirect('review', pk=pk)
                    plan.status = 'APPROVED'
                    plan.approved_at = timezone.now()
                    plan.reviewed_by = request.user
                plan.save()
                formset.save()
                messages.success(request, 'Intervention approved and assigned to the learner.' if action == 'approve' else 'Draft changes saved.')
                return redirect('review', pk=pk)
    return render(request, 'core/review.html', {'plan': plan, 'form': form, 'formset': formset, 'missions': plan.missions.all(), 'completed_count': recovery_progress_count(plan)})


@login_required
@require_POST
def share_toggle(request, pk):
    journey = get_object_or_404(Journey, pk=pk, learner=request.user)
    if journey.share_enabled:
        journey.share_enabled = False
        journey.shared_milestone = None
        journey.share_token = secrets.token_urlsafe()
        messages.success(request, 'Sharing disabled. The previous link is revoked.')
    else:
        earned = [m for m in milestones_for(journey) if m.earned and str(m.pk) == request.POST.get('milestone')]
        if not earned:
            messages.error(request, 'Select a milestone with all lesson competencies demonstrated.')
            return redirect('journey', pk=pk)
        journey.shared_milestone = earned[0]
        journey.share_enabled = True
        messages.success(request, 'Your selected achievement is ready to share.')
    journey.save(update_fields=['share_enabled', 'shared_milestone', 'share_token'])
    return redirect('journey', pk=pk)


def circle(request, token):
    journey = get_object_or_404(Journey.objects.select_related('shared_milestone', 'learner', 'course'), share_token=token, share_enabled=True, shared_milestone__isnull=False)
    milestone = next((m for m in milestones_for(journey) if m.pk == journey.shared_milestone_id and m.earned), None)
    if not milestone:
        from django.http import Http404
        raise Http404
    choices = ['Proud of you!', 'Keep going!', 'You’ve got this!', 'Congratulations!']
    if request.method == 'POST':
        message = request.POST.get('message')
        if message not in choices:
            messages.error(request, 'Select a valid encouragement.')
        elif request.session.get('encouraged_' + token):
            messages.info(request, 'You already sent encouragement during this visit.')
        else:
            Encouragement.objects.create(journey=journey, message=message)
            request.session['encouraged_' + token] = True
            messages.success(request, 'Encouragement sent!')
        return redirect('circle', token=token)
    response = render(request, 'core/circle.html', {'journey': journey, 'milestone': milestone, 'choices': choices})
    response['Cache-Control'] = 'private, no-store'
    response['X-Robots-Tag'] = 'noindex, nofollow'
    response['Referrer-Policy'] = 'no-referrer'
    return response
