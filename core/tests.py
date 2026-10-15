from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from .models import Course,Milestone,Lesson,Question,Journey,LessonProgress,RecoveryPlan,Encouragement
from .services import PLANS,momentum

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], OPENAI_API_KEY='')
class ComebackTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='learner',password='safe-pass-12345')
        self.other=User.objects.create_user(username='other',password='safe-pass-12345')
        self.course=Course.objects.create(title='Python Basics')
        self.milestone=Milestone.objects.create(course=self.course,title='Functions')
        self.lesson=Lesson.objects.create(milestone=self.milestone,title='Define functions',content='Use def')
        self.q=Question.objects.create(lesson=self.lesson,prompt='Keyword?',option_a='def',option_b='if',option_c='for',correct='A')
        self.journey=Journey.objects.create(learner=self.user,course=self.course)
    def test_momentum_is_bounded(self):
        self.assertTrue(0<=momentum(self.journey)<=100)
    def test_recovery_requires_login_and_ownership(self):
        self.client.force_login(self.other)
        response=self.client.post(reverse('checkin',args=[self.journey.pk]),{'reason':'TIME'})
        self.assertEqual(response.status_code,404)
    def test_checkin_creates_pending_recommendation(self):
        self.client.force_login(self.user)
        self.client.post(reverse('checkin',args=[self.journey.pk]),{'reason':'DIFFICULTY'})
        plan=RecoveryPlan.objects.get(journey=self.journey)
        self.assertEqual(plan.status,'PENDING')
        self.assertIn('simpler explanation',plan.recommended_action)
        self.assertEqual(plan.missions.count(), 3)
    def test_quiz_marks_competency_after_pass(self):
        self.client.force_login(self.user)
        self.client.post(reverse('lesson',args=[self.lesson.pk]),{'journey':self.journey.pk,f'q_{self.q.pk}':'A'})
        self.assertTrue(LessonProgress.objects.get(journey=self.journey,lesson=self.lesson).completed)
    def test_quiz_does_not_mark_competency_after_fail(self):
        self.client.force_login(self.user)
        self.client.post(reverse('lesson',args=[self.lesson.pk]),{'journey':self.journey.pk,f'q_{self.q.pk}':'B'})
        self.assertFalse(LessonProgress.objects.get(journey=self.journey,lesson=self.lesson).completed)
    def test_private_circle_is_inaccessible(self):
        response=self.client.get(reverse('circle',args=[self.journey.share_token]))
        self.assertEqual(response.status_code,404)
    def test_circle_restricts_messages(self):
        self.journey.share_enabled=True;self.journey.save()
        self.client.post(reverse('circle',args=[self.journey.share_token]),{'message':'<script>alert(1)</script>'})
        self.assertFalse(Encouragement.objects.exists())
    def test_recovery_cannot_be_marked_without_admin_approval(self):
        self.client.force_login(self.user)
        self.client.post(reverse('checkin',args=[self.journey.pk]),{'reason':'TIME'})
        plan=RecoveryPlan.objects.get()
        self.client.post(reverse('recovery',args=[plan.pk]))
        plan.refresh_from_db();self.assertEqual(plan.status,'PENDING')
