import io
import json
from datetime import timedelta
from unittest.mock import patch
from urllib.error import URLError
from django.test import Client, TestCase, override_settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from .models import Journey, Lesson, Question, LessonProgress, Attempt, CheckIn, RecoveryPlan, Encouragement, StudySession
from .services import create_recovery, evaluate_recovery, signals, risk_reasons
from .ai import personalize


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], OPENAI_API_KEY='')
class WorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_scenarios', password='Demo-Password-123!', stdout=io.StringIO())
        cls.tunde = User.objects.get(username='tunde')
        cls.amina = User.objects.get(username='amina')
        cls.educator = User.objects.get(username='educator')

    def setUp(self):
        self.journey = Journey.objects.get(learner=self.tunde)

    def plan(self, reason='DIFFICULTY', journey=None):
        journey = journey or self.journey
        return create_recovery(CheckIn.objects.create(journey=journey, reason=reason), use_ai=False)

    def assigned(self):
        plan = self.plan()
        plan.status = 'APPROVED'
        plan.approved_at = timezone.now() - timedelta(minutes=30)
        plan.save()
        return plan

    def complete_missions(self, plan):
        plan.missions.update(completed_at=timezone.now() - timedelta(minutes=1), reflection='I practiced the example and explained the result.')

    def answers(self, plan, correct=True):
        data = {'journey': self.journey.pk, 'plan': plan.pk}
        for q in plan.target_lesson.questions.filter(is_followup=True):
            data[f'q_{q.pk}'] = q.correct if correct else next(a for a in 'ABC' if a != q.correct)
        return data

    def review_data(self, plan, action='approve'):
        data = {'action': action, 'recommended_action': 'An educator-reviewed explanation and guided practice.', 'admin_feedback': 'Take your time and trace each input.',
            'missions-TOTAL_FORMS': '3', 'missions-INITIAL_FORMS': '3', 'missions-MIN_NUM_FORMS': '3', 'missions-MAX_NUM_FORMS': '3'}
        for i, m in enumerate(plan.missions.all()):
            for key, value in {'id': m.pk, 'plan': plan.pk, 'title': m.title, 'instructions': m.instructions, 'minutes': m.minutes}.items():
                data[f'missions-{i}-{key}'] = value
        return data

    def test_two_histories_produce_distinct_plans_without_identity_rules(self):
        t = self.plan()
        a = self.plan('TIME', Journey.objects.get(learner=self.amina))
        self.assertEqual(t.baseline_score, 33)
        self.assertIsNone(a.baseline_score)
        self.assertEqual(t.target_lesson.title, 'Parameters and Returns')
        self.assertEqual(a.target_lesson.title, 'Data Types')
        self.assertEqual(a.evidence['missed_sessions'], 3)
        self.assertEqual(a.evidence['recent_scores'], [100, 100])
        self.assertNotEqual(t.step_one, a.step_one)
        self.assertEqual(t.generation_source, 'RULES')
        self.tunde.username = 'renamed-learner'
        self.tunde.save()
        self.assertIn('simpler explanation', t.recommended_action)

    def test_duplicate_checkin_does_not_duplicate_active_plan(self):
        self.client.force_login(self.tunde)
        url = reverse('checkin', args=[self.journey.pk])
        self.client.post(url, {'reason': 'DIFFICULTY'})
        self.client.post(url, {'reason': 'TIME'})
        self.assertEqual(RecoveryPlan.objects.count(), 1)
        self.assertEqual(CheckIn.objects.count(), 1)

    def test_unrecognized_challenge_rejected(self):
        self.client.force_login(self.tunde)
        self.client.post(reverse('checkin', args=[self.journey.pk]), {'reason': 'CONNECTIVITY'})
        self.assertFalse(RecoveryPlan.objects.exists())

    def test_learner_cannot_access_educator_views(self):
        plan = self.plan()
        self.client.force_login(self.tunde)
        for url in [reverse('educator'), reverse('educator_learner', args=[self.journey.pk]), reverse('review', args=[plan.pk])]:
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(reverse('review', args=[plan.pk]), self.review_data(plan)).status_code, 403)

    def test_educator_can_edit_approve_and_assign(self):
        plan = self.plan()
        self.client.force_login(self.educator)
        data = self.review_data(plan)
        data['missions-0-title'] = 'A clearer explanation of function inputs'
        response = self.client.post(reverse('review', args=[plan.pk]), data)
        self.assertEqual(response.status_code, 302)
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'APPROVED')
        self.assertEqual(plan.reviewed_by, self.educator)
        self.assertIsNotNone(plan.approved_at)
        self.assertEqual(plan.missions.first().title, data['missions-0-title'])
        self.client.post(reverse('review', args=[plan.pk]), self.review_data(plan, 'close'))
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'APPROVED')

    def test_invalid_mission_cannot_be_assigned(self):
        plan = self.plan()
        self.client.force_login(self.educator)
        data = self.review_data(plan)
        data['missions-1-minutes'] = '0'
        self.assertEqual(self.client.post(reverse('review', args=[plan.pk]), data).status_code, 200)
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'PENDING')

    def test_draft_save_and_close(self):
        plan = self.plan()
        self.client.force_login(self.educator)
        self.client.post(reverse('review', args=[plan.pk]), self.review_data(plan, 'save'))
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'PENDING')
        self.client.post(reverse('review', args=[plan.pk]), {'action': 'close', 'admin_feedback': 'Please confirm your current challenge.'})
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'CANCELLED')
        self.assertNotEqual(self.plan().pk, plan.pk)

    def test_pending_missions_and_early_reassessment_blocked(self):
        plan = self.plan()
        self.client.force_login(self.tunde)
        m = plan.missions.first()
        self.client.post(reverse('recovery', args=[plan.pk]), {'action': 'mission', 'mission': m.pk, 'reflection': 'I completed my practice example.'})
        m.refresh_from_db()
        self.assertIsNone(m.completed_at)
        plan.status = 'APPROVED'
        plan.approved_at = timezone.now()
        plan.save()
        self.client.post(reverse('lesson', args=[plan.target_lesson_id]), self.answers(plan))
        self.assertFalse(plan.assessments.exists())

    def test_missions_require_order_and_substantial_reflection(self):
        plan = self.assigned()
        self.client.force_login(self.tunde)
        missions = list(plan.missions.all())
        url = reverse('recovery', args=[plan.pk])
        self.client.post(url, {'action': 'mission', 'mission': missions[1].pk, 'reflection': 'I worked through an example of a function.'})
        self.client.post(url, {'action': 'mission', 'mission': missions[0].pk, 'reflection': 'done'})
        self.assertFalse(plan.missions.filter(completed_at__isnull=False).exists())
        for m in missions:
            self.client.post(url, {'action': 'mission', 'mission': m.pk, 'reflection': 'The parameter receives 3 and the return sends 6 back.'})
        self.assertEqual(plan.missions.filter(completed_at__isnull=False).count(), 3)
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'APPROVED')

    def test_failed_reassessment_never_counts_as_recovery(self):
        plan = self.assigned()
        self.complete_missions(plan)
        self.client.force_login(self.tunde)
        response = self.client.post(reverse('lesson', args=[plan.target_lesson_id]), self.answers(plan, False), follow=True)
        self.assertEqual(response.status_code, 200)
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'APPROVED')
        self.assertEqual(plan.followup_score, 0)
        self.assertIsNone(plan.completed_at)

    def test_full_recovery_unlocks_milestone_and_sharing(self):
        plan = self.assigned()
        self.complete_missions(plan)
        self.client.force_login(self.tunde)
        response = self.client.post(reverse('lesson', args=[plan.target_lesson_id]), self.answers(plan), follow=True)
        self.assertContains(response, 'This is your comeback.')
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'COMPLETED')
        self.assertEqual(plan.followup_score, 100)
        next_lesson = Lesson.objects.get(title='Lists')
        self.assertEqual(self.client.get(reverse('lesson', args=[next_lesson.pk]), {'journey': self.journey.pk}).status_code, 200)
        self.client.post(reverse('share_toggle', args=[self.journey.pk]), {'milestone': plan.target_lesson.milestone_id})
        self.journey.refresh_from_db()
        self.assertTrue(self.journey.share_enabled)
        response = self.client.get(reverse('circle', args=[self.journey.share_token]))
        self.assertContains(response, 'Functions')
        self.assertNotContains(response, '33%')
        self.assertNotContains(response, 'Difficult concepts')

    def test_unrelated_and_stale_attempts_do_not_count(self):
        plan = self.assigned()
        self.complete_missions(plan)
        unrelated = Attempt.objects.create(journey=self.journey, lesson=Lesson.objects.get(title='Lists'), score=100, recovery_plan=plan)
        self.assertFalse(evaluate_recovery(plan, unrelated))
        stale = Attempt.objects.create(journey=self.journey, lesson=plan.target_lesson, score=100, recovery_plan=plan)
        Attempt.objects.filter(pk=stale.pk).update(created_at=plan.approved_at - timedelta(minutes=1))
        stale.refresh_from_db()
        self.assertFalse(evaluate_recovery(plan, stale))
        ordinary = Attempt.objects.create(journey=self.journey, lesson=plan.target_lesson, score=100)
        self.assertFalse(evaluate_recovery(plan, ordinary))

    def test_amina_time_recovery_uses_new_competency(self):
        self.journey = Journey.objects.get(learner=self.amina)
        plan = self.plan('TIME', self.journey)
        plan.status = 'APPROVED'
        plan.approved_at = timezone.now() - timedelta(minutes=30)
        plan.save()
        self.complete_missions(plan)
        self.client.force_login(self.amina)
        self.client.post(reverse('lesson', args=[plan.target_lesson_id]), self.answers(plan))
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'COMPLETED')
        self.assertIsNone(plan.baseline_score)
        self.assertEqual(plan.followup_score, 100)
        self.assertIn('2 → 3', plan.outcome)

    def test_locked_lesson_cannot_be_completed_by_direct_post(self):
        lesson = Lesson.objects.get(title='Lists')
        self.client.force_login(self.tunde)
        data = {'journey': self.journey.pk}
        data.update({f'q_{q.pk}': q.correct for q in lesson.questions.filter(is_followup=False)})
        self.assertEqual(self.client.post(reverse('lesson', args=[lesson.pk]), data).status_code, 302)
        self.assertFalse(Attempt.objects.filter(journey=self.journey, lesson=lesson).exists())

    def test_other_learner_cannot_read_or_mutate_journey(self):
        plan = self.assigned()
        self.client.force_login(self.amina)
        for url in [reverse('journey', args=[self.journey.pk]), reverse('recovery', args=[plan.pk]), reverse('checkin', args=[self.journey.pk])]:
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {}).status_code, 404)
        self.assertEqual(self.client.post(reverse('lesson', args=[plan.target_lesson_id]), self.answers(plan)).status_code, 404)

    def test_only_earned_milestone_can_be_shared_and_revocation_rotates_token(self):
        self.client.force_login(self.tunde)
        unearned = Lesson.objects.get(title='Lists').milestone
        self.client.post(reverse('share_toggle', args=[self.journey.pk]), {'milestone': unearned.pk})
        self.journey.refresh_from_db()
        self.assertFalse(self.journey.share_enabled)
        earned = Lesson.objects.get(title='What is Python?').milestone
        self.client.post(reverse('share_toggle', args=[self.journey.pk]), {'milestone': earned.pk})
        self.journey.refresh_from_db()
        token = self.journey.share_token
        self.client.logout()
        self.client.post(reverse('circle', args=[token]), {'message': 'Proud of you!'})
        self.client.post(reverse('circle', args=[token]), {'message': 'Keep going!'})
        self.assertEqual(Encouragement.objects.count(), 1)
        self.client.force_login(self.tunde)
        self.client.post(reverse('share_toggle', args=[self.journey.pk]))
        self.journey.refresh_from_db()
        self.assertNotEqual(token, self.journey.share_token)
        self.assertEqual(self.client.get(reverse('circle', args=[token])).status_code, 404)
        self.client.post(reverse('share_toggle', args=[self.journey.pk]), {'milestone': earned.pk})
        self.assertEqual(self.client.get(reverse('circle', args=[token])).status_code, 404)

    def test_session_scheduling_and_missed_session_evidence(self):
        self.client.force_login(self.tunde)
        url = reverse('journey', args=[self.journey.pk])
        response = self.client.post(url, {'action': 'schedule', 'scheduled_for': (timezone.now()-timedelta(days=1)).isoformat()})
        self.assertContains(response, 'Choose a future session')
        future = timezone.now()+timedelta(days=1)
        self.client.post(url, {'action': 'schedule', 'scheduled_for': future.isoformat()})
        self.assertEqual(self.journey.sessions.count(), 1)
        missed = StudySession.objects.create(journey=self.journey, scheduled_for=timezone.now()-timedelta(days=1))
        self.assertEqual(signals(self.journey)['missed_sessions'], 1)
        self.assertTrue(any('planned session' in r for r in risk_reasons(self.journey)))
        missed.refresh_from_db()
        self.assertIsNone(missed.completed_at)

    def test_templates_render_for_both_roles(self):
        plan = self.plan()
        self.client.force_login(self.tunde)
        for url in [reverse('home'), reverse('dashboard'), reverse('journey', args=[self.journey.pk]), reverse('recovery', args=[plan.pk])]:
            self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.educator)
        for url in [reverse('educator'), reverse('educator_learner', args=[self.journey.pk]), reverse('review', args=[plan.pk])]:
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_seeding_is_idempotent_and_preserves_accounts(self):
        before = (User.objects.count(), Attempt.objects.count(), Question.objects.count())
        call_command('seed_scenarios', password='Different-Password-123!', stdout=io.StringIO())
        self.assertEqual(before, (User.objects.count(), Attempt.objects.count(), Question.objects.count()))
        self.assertTrue(User.objects.get(pk=self.tunde.pk).check_password('Demo-Password-123!'))

    def test_malformed_identifiers_return_404_not_server_errors(self):
        plan = self.assigned()
        self.client.force_login(self.tunde)
        for bad_id in ['invalid', '-1', '9' * 100]:
            with self.subTest(bad_id=bad_id):
                self.assertEqual(self.client.get(reverse('lesson', args=[plan.target_lesson_id]), {'journey': bad_id}).status_code, 404)
                self.assertEqual(self.client.get(reverse('lesson', args=[plan.target_lesson_id]), {'journey': self.journey.pk, 'plan': bad_id}).status_code, 404)
                self.assertEqual(self.client.post(reverse('recovery', args=[plan.pk]), {'action': 'mission', 'mission': bad_id}).status_code, 404)

    def test_today_session_is_not_missed_until_utc_day_ends(self):
        now = timezone.now().replace(hour=12, minute=0, second=0)
        StudySession.objects.create(journey=self.journey, scheduled_for=now - timedelta(hours=2))
        with patch('django.utils.timezone.now', return_value=now):
            self.assertEqual(signals(self.journey)['missed_sessions'], 0)
            self.client.force_login(self.tunde)
            response = self.client.get(reverse('journey', args=[self.journey.pk]))
            self.assertNotContains(response, '>Missed<')
        with patch('django.utils.timezone.now', return_value=now + timedelta(days=1)):
            self.assertEqual(signals(self.journey)['missed_sessions'], 1)

    def test_recovery_snapshot_does_not_change_after_later_learning(self):
        plan = self.assigned()
        self.complete_missions(plan)
        self.client.force_login(self.tunde)
        self.client.post(reverse('lesson', args=[plan.target_lesson_id]), self.answers(plan))
        extra = Lesson.objects.get(title='Lists')
        LessonProgress.objects.create(journey=self.journey, lesson=extra, completed=True, attempts=1, best_score=100)
        response = self.client.get(reverse('recovery', args=[plan.pk]))
        self.assertEqual(response.context['completed_count'], 8)
        self.client.force_login(self.educator)
        self.assertEqual(self.client.get(reverse('review', args=[plan.pk])).context['completed_count'], 8)

    def test_review_rejects_duplicate_mission_ids(self):
        plan = self.plan()
        self.client.force_login(self.educator)
        data = self.review_data(plan)
        data['missions-1-id'] = data['missions-0-id']
        response = self.client.post(reverse('review', args=[plan.pk]), data)
        self.assertEqual(response.status_code, 200)
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'PENDING')

    def test_review_rejects_forged_initial_form_count(self):
        plan = self.plan()
        self.client.force_login(self.educator)
        data = self.review_data(plan)
        data['missions-INITIAL_FORMS'] = '0'
        self.assertEqual(self.client.post(reverse('review', args=[plan.pk]), data).status_code, 200)
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'PENDING')

    def test_review_cannot_substitute_another_learners_mission(self):
        plan = self.plan()
        other = self.plan('TIME', Journey.objects.get(learner=self.amina))
        self.client.force_login(self.educator)
        data = self.review_data(plan)
        data['missions-0-id'] = other.missions.first().pk
        self.assertEqual(self.client.post(reverse('review', args=[plan.pk]), data).status_code, 200)
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'PENDING')
        self.assertEqual(other.missions.first().title, 'One idea, one short session')

    def test_signup_and_all_eleven_lessons_complete_a_fresh_course(self):
        response = self.client.post(reverse('register'), {'username': 'new-learner', 'password1': 'River-Quartz-4829!', 'password2': 'River-Quartz-4829!', 'is_staff': '1'}, follow=True)
        self.assertEqual(response.status_code, 200)
        learner = User.objects.get(username='new-learner')
        self.assertFalse(learner.is_staff)
        self.client.post(reverse('start', args=[self.journey.course_id]))
        journey = Journey.objects.get(learner=learner)
        for lesson in Lesson.objects.filter(milestone__course=journey.course).order_by('milestone__order', 'order'):
            data = {'journey': journey.pk}
            data.update({f'q_{q.pk}': q.correct for q in lesson.questions.filter(is_followup=False)})
            response = self.client.post(reverse('lesson', args=[lesson.pk]), data, follow=True)
            self.assertContains(response, 'Competency demonstrated')
        self.assertEqual(journey.progress.filter(completed=True).count(), 11)
        self.assertEqual(Attempt.objects.filter(journey=journey).count(), 11)
        response = self.client.get(reverse('journey', args=[journey.pk]))
        self.assertEqual(len(response.context['earned']), 4)
        self.client.post(reverse('checkin', args=[journey.pk]), {'reason': 'DIFFICULTY'})
        self.assertFalse(journey.recovery_plans.exists())

    def test_motivation_workflow_through_real_forms(self):
        self.journey = Journey.objects.get(learner=self.amina)
        self.client.force_login(self.amina)
        self.client.post(reverse('journey', args=[self.journey.pk]), {'action': 'preferences', 'daily_minutes': 5, 'learning_goal': 'Build a small budgeting program'})
        self.client.post(reverse('checkin', args=[self.journey.pk]), {'reason': 'MOTIVATION', 'note': 'I want to reconnect with my goal.'})
        plan = self.journey.recovery_plans.get()
        self.assertIn('budgeting program', plan.missions.first().instructions)
        self.assertEqual(list(plan.missions.values_list('minutes', flat=True)), [5, 5, 5])
        self.client.force_login(self.educator)
        self.assertEqual(self.client.post(reverse('review', args=[plan.pk]), self.review_data(plan)).status_code, 302)
        self.client.force_login(self.amina)
        for m in plan.missions.all():
            response = self.client.post(reverse('recovery', args=[plan.pk]), {'action': 'mission', 'mission': m.pk, 'reflection': 'A price of 2.5 is a float; a label such as food is a string.'}, follow=True)
            self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Take the recovery competency check')
        self.client.post(reverse('lesson', args=[plan.target_lesson_id]), self.answers(plan, False))
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'APPROVED')
        response = self.client.post(reverse('lesson', args=[plan.target_lesson_id]), self.answers(plan), follow=True)
        self.assertContains(response, 'This is your comeback.')
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'COMPLETED')
        self.assertEqual(plan.assessments.count(), 2)
        self.assertEqual(plan.evidence['followup_completed'], 3)
        self.client.post(reverse('share_toggle', args=[self.journey.pk]), {'milestone': plan.target_lesson.milestone_id})
        self.journey.refresh_from_db()
        supporter = Client()
        url = reverse('circle', args=[self.journey.share_token])
        self.assertEqual(supporter.post(url, {'message': 'Proud of you!'}).status_code, 302)
        self.assertContains(self.client.get(reverse('journey', args=[self.journey.pk])), 'Proud of you!')
        self.assertEqual(supporter.get(url)['Cache-Control'], 'private, no-store')

    def test_csrf_protection_for_learner_and_educator_mutations(self):
        plan = self.plan()
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.tunde)
        for url, data in [(reverse('checkin', args=[self.journey.pk]), {'reason': 'TIME'}),
                          (reverse('share_toggle', args=[self.journey.pk]), {}),
                          (reverse('lesson', args=[plan.target_lesson_id]), self.answers(plan))]:
            self.assertEqual(protected.post(url, data).status_code, 403)
        protected.force_login(self.educator)
        self.assertEqual(protected.post(reverse('review', args=[plan.pk]), self.review_data(plan)).status_code, 403)
        protected.get(reverse('review', args=[plan.pk]))
        data = self.review_data(plan)
        data['csrfmiddlewaretoken'] = protected.cookies['csrftoken'].value
        self.assertEqual(protected.post(reverse('review', args=[plan.pk]), data).status_code, 302)

    def test_incomplete_quiz_does_not_record_an_attempt(self):
        plan = self.plan()
        self.client.force_login(self.tunde)
        before = Attempt.objects.filter(journey=self.journey).count()
        response = self.client.post(reverse('lesson', args=[plan.target_lesson_id]), {'journey': self.journey.pk})
        self.assertContains(response, 'Please answer every question')
        self.assertEqual(Attempt.objects.filter(journey=self.journey).count(), before)

    def test_legacy_recovery_without_snapshot_shows_unknown_total(self):
        plan = self.assigned()
        plan.status = 'COMPLETED'
        plan.followup_score = 100
        plan.save()
        self.client.force_login(self.tunde)
        response = self.client.get(reverse('recovery', args=[plan.pk]))
        self.assertIsNone(response.context['completed_count'])
        self.assertContains(response, 'not recorded')

    @override_settings(OPENAI_API_KEY='test-only')
    def test_ai_success_and_failure_are_labelled_and_validated(self):
        check = CheckIn.objects.create(journey=self.journey, reason='DIFFICULTY')
        lesson = Lesson.objects.get(title='Parameters and Returns')
        valid = {'recommendation': 'Provide a worked example of return values.', 'missions': [
            {'title': f'Mission {i}', 'instructions': 'Trace a function that doubles its input and explain the result.', 'minutes': 10} for i in range(3)]}
        payload = {'status': 'completed', 'output': [{'content': [{'type': 'output_text', 'text': json.dumps(valid)}]}]}
        with patch('core.ai.urlopen') as send:
            send.return_value.__enter__.return_value = io.StringIO(json.dumps(payload))
            result, note = personalize(check, lesson, {}, [])
            self.assertEqual(result, valid)
            self.assertIn('Personalized', note)
            body = json.loads(send.call_args.args[0].data)
            self.assertFalse(body['store'])
            self.assertTrue(body['text']['format']['strict'])
        with patch('core.ai.urlopen', side_effect=URLError('offline')):
            plan = create_recovery(check)
            self.assertEqual(plan.generation_source, 'RULES')
            self.assertIn('unavailable', plan.generation_note)
        valid['missions'] = valid['missions'][:2]
        payload['output'][0]['content'][0]['text'] = json.dumps(valid)
        with patch('core.ai.urlopen') as send:
            send.return_value.__enter__.return_value = io.StringIO(json.dumps(payload))
            self.assertIsNone(personalize(check, lesson, {}, [])[0])
