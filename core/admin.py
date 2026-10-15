from django.contrib import admin
from .models import Course,Milestone,Lesson,Question,Journey,LessonProgress,Attempt,CheckIn,RecoveryPlan,Encouragement
for model in [Course,Milestone,Lesson,Question,Journey,LessonProgress,Attempt,CheckIn,Encouragement]: admin.site.register(model)
@admin.register(RecoveryPlan)
class RecoveryPlanAdmin(admin.ModelAdmin):
    list_display=('journey','status','recommended_action','created_at')
    list_filter=('status',)
    # Assignment is performed in the educator portal, with mission validation.
    readonly_fields = [field.name for field in RecoveryPlan._meta.fields]
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
