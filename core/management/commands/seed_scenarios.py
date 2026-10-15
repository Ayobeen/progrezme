import secrets
from datetime import timedelta
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from core.models import Course, Lesson, Journey, LessonProgress, Attempt, StudySession, LearningEvent

class Command(BaseCommand):
    help = 'Create fictional Tunde/Amina histories and an educator for a local demo; existing accounts are never overwritten.'

    def add_arguments(self, parser):
        parser.add_argument('--password', help='Optional local demo password; otherwise a random password is generated.')

    @transaction.atomic
    def handle(self, *args, **options):
        call_command('seed_demo')
        password = options['password'] or secrets.token_urlsafe(14)
        if len(password) < 10:
            raise CommandError('Use at least 10 characters for the demo password.')
        course = Course.objects.get(title='Python Basics')
        lessons = list(Lesson.objects.filter(milestone__course=course).order_by('milestone__order', 'order'))
        now = timezone.now()
        created = []
        for username, completed, days in [('tunde', 7, 4), ('amina', 2, 6), ('educator', None, 0)]:
            if User.objects.filter(username=username).exists():
                self.stdout.write(f'{username}: already exists; account and learning history preserved.')
                continue
            user = User.objects.create_user(username=username, password=password, is_staff=username == 'educator')
            created.append(username)
            if completed is None:
                continue
            journey = Journey.objects.create(learner=user, course=course, daily_minutes=10 if username == 'amina' else 15,
                learning_goal='Use Python to solve everyday problems')
            Journey.objects.filter(pk=journey.pk).update(last_active_at=now - timedelta(days=days))
            for i, lesson in enumerate(lessons[:completed]):
                LessonProgress.objects.create(journey=journey, lesson=lesson, completed=True, attempts=1, best_score=100)
                attempt = Attempt.objects.create(journey=journey, lesson=lesson, score=100)
                Attempt.objects.filter(pk=attempt.pk).update(created_at=now - timedelta(days=days + completed - i))
                event = LearningEvent.objects.create(journey=journey, lesson=lesson, kind='QUIZ')
                LearningEvent.objects.filter(pk=event.pk).update(created_at=now - timedelta(days=days + completed - i))
            if username == 'tunde':
                target = lessons[7]
                LessonProgress.objects.create(journey=journey, lesson=target, attempts=2, best_score=33)
                for hours in [2, 0]:
                    attempt = Attempt.objects.create(journey=journey, lesson=target, score=33)
                    Attempt.objects.filter(pk=attempt.pk).update(created_at=now - timedelta(days=days, hours=hours))
            else:
                for missed in [5, 3, 1]:
                    StudySession.objects.create(journey=journey, scheduled_for=now - timedelta(days=missed))
        if created:
            self.stdout.write(self.style.SUCCESS('Created fictional demo accounts: ' + ', '.join(created)))
            self.stdout.write('Local demo password: ' + password)
            self.stdout.write('Sign in as each learner to confirm their challenge, then as educator to review and assign.')
        else:
            self.stdout.write('No accounts changed. Use changepassword if you need to reset a local demo login.')
