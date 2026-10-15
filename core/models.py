import secrets
from django.conf import settings
from django.db import models

class Course(models.Model):
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    def __str__(self): return self.title

class Milestone(models.Model):
    course = models.ForeignKey(Course,on_delete=models.CASCADE,related_name='milestones')
    title = models.CharField(max_length=150)
    order = models.PositiveIntegerField(default=0)
    class Meta: ordering=['order','id']
    def __str__(self): return self.title

class Lesson(models.Model):
    milestone = models.ForeignKey(Milestone,on_delete=models.CASCADE,related_name='lessons')
    title = models.CharField(max_length=150)
    content = models.TextField()
    order = models.PositiveIntegerField(default=0)
    class Meta: ordering=['order','id']
    def __str__(self): return self.title

class Question(models.Model):
    lesson = models.ForeignKey(Lesson,on_delete=models.CASCADE,related_name='questions')
    prompt = models.TextField()
    option_a = models.CharField(max_length=250)
    option_b = models.CharField(max_length=250)
    option_c = models.CharField(max_length=250)
    correct = models.CharField(max_length=1,choices=[(x,x) for x in 'ABC'])
    explanation = models.TextField(blank=True)
    is_followup = models.BooleanField(default=False)

class Journey(models.Model):
    learner = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='journeys')
    course = models.ForeignKey(Course,on_delete=models.CASCADE)
    daily_minutes = models.PositiveIntegerField(default=30)
    last_active_at = models.DateTimeField(auto_now_add=True)
    share_token = models.CharField(max_length=48,unique=True,default=secrets.token_urlsafe)
    share_enabled = models.BooleanField(default=False)
    shared_milestone = models.ForeignKey(Milestone, null=True, blank=True, on_delete=models.SET_NULL)
    learning_goal = models.CharField(max_length=250, blank=True)
    class Meta: constraints=[models.UniqueConstraint(fields=['learner','course'],name='one_journey_per_course')]

class LessonProgress(models.Model):
    journey = models.ForeignKey(Journey,on_delete=models.CASCADE,related_name='progress')
    lesson = models.ForeignKey(Lesson,on_delete=models.CASCADE)
    completed = models.BooleanField(default=False)
    attempts = models.PositiveIntegerField(default=0)
    best_score = models.PositiveIntegerField(default=0)
    class Meta: constraints=[models.UniqueConstraint(fields=['journey','lesson'],name='one_progress_per_lesson')]

class Attempt(models.Model):
    journey = models.ForeignKey(Journey,on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson,on_delete=models.CASCADE)
    score = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    recovery_plan = models.ForeignKey('RecoveryPlan', null=True, blank=True, on_delete=models.SET_NULL, related_name='assessments')

class CheckIn(models.Model):
    REASONS=[('TIME','Not enough time'),('DIFFICULTY','Difficult concepts'),('MOTIVATION','Low motivation')]
    journey = models.ForeignKey(Journey,on_delete=models.CASCADE,related_name='checkins')
    reason = models.CharField(max_length=20,choices=REASONS)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class RecoveryPlan(models.Model):
    STATUSES=[('PENDING','Awaiting educator review'),('APPROVED','Assigned'),('COMPLETED','Recovery evidenced'),('CANCELLED','Closed')]
    journey = models.ForeignKey(Journey,on_delete=models.CASCADE,related_name='recovery_plans')
    checkin = models.OneToOneField(CheckIn,on_delete=models.CASCADE)
    status = models.CharField(max_length=12,choices=STATUSES,default='PENDING')
    recommended_action = models.TextField()
    step_one = models.CharField(max_length=250)
    step_two = models.CharField(max_length=250)
    step_three = models.CharField(max_length=250)
    admin_feedback = models.TextField(blank=True)
    baseline_score = models.PositiveIntegerField(null=True, blank=True)
    followup_score = models.PositiveIntegerField(null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True,blank=True)
    completed_at = models.DateTimeField(null=True,blank=True)
    target_lesson = models.ForeignKey(Lesson, null=True, blank=True, on_delete=models.PROTECT)
    baseline_completed = models.PositiveIntegerField(default=0)
    evidence = models.JSONField(default=dict)
    generation_source = models.CharField(max_length=20, default='RULES')
    generation_note = models.CharField(max_length=250, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_plans')
    outcome = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['journey'], condition=models.Q(status__in=['PENDING', 'APPROVED']), name='one_active_recovery')]

class RecoveryMission(models.Model):
    plan = models.ForeignKey(RecoveryPlan, on_delete=models.CASCADE, related_name='missions')
    order = models.PositiveIntegerField()
    title = models.CharField(max_length=160)
    instructions = models.TextField()
    minutes = models.PositiveIntegerField(default=10)
    reflection = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ['order']
        constraints = [models.UniqueConstraint(fields=['plan', 'order'], name='unique_mission_order')]

class StudySession(models.Model):
    journey = models.ForeignKey(Journey, on_delete=models.CASCADE, related_name='sessions')
    scheduled_for = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ['scheduled_for']
        constraints = [models.UniqueConstraint(fields=['journey', 'scheduled_for'], name='unique_session_time')]

class LearningEvent(models.Model):
    journey = models.ForeignKey(Journey, on_delete=models.CASCADE, related_name='events')
    lesson = models.ForeignKey(Lesson, null=True, blank=True, on_delete=models.SET_NULL)
    kind = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

class Encouragement(models.Model):
    journey = models.ForeignKey(Journey,on_delete=models.CASCADE,related_name='encouragements')
    message = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
