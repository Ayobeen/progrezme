from django import forms
from django.utils import timezone
from .models import RecoveryPlan, RecoveryMission, StudySession, Journey

class ReviewForm(forms.ModelForm):
    class Meta:
        model = RecoveryPlan
        fields = ['recommended_action', 'admin_feedback']
        labels = {'recommended_action': 'Recommended intervention', 'admin_feedback': 'Your guidance to the learner'}
        widgets = {'recommended_action': forms.Textarea(attrs={'rows': 3}), 'admin_feedback': forms.Textarea(attrs={'rows': 3})}

class MissionForm(forms.ModelForm):
    minutes = forms.IntegerField(min_value=5, max_value=15)
    class Meta:
        model = RecoveryMission
        fields = ['title', 'instructions', 'minutes']
        widgets = {'instructions': forms.Textarea(attrs={'rows': 5})}

class ExistingMissionFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        expected = set(self.get_queryset().values_list('pk', flat=True))
        submitted = [form.cleaned_data.get('id') for form in self.forms]
        ids = [mission.pk for mission in submitted if mission is not None]
        if (self.initial_form_count() != 3 or len(expected) != 3
                or len(ids) != 3 or set(ids) != expected):
            raise forms.ValidationError('Review all three original missions exactly once. Reload the plan and try again.')


MissionFormSet = forms.inlineformset_factory(RecoveryPlan, RecoveryMission, form=MissionForm, formset=ExistingMissionFormSet, extra=0, can_delete=False, min_num=3, max_num=3, validate_min=True, validate_max=True)

class SessionForm(forms.ModelForm):
    class Meta:
        model = StudySession
        fields = ['scheduled_for']
        widgets = {'scheduled_for': forms.DateTimeInput(attrs={'type': 'datetime-local'})}
        labels = {'scheduled_for': 'Next session (UTC)'}
    def clean_scheduled_for(self):
        value = self.cleaned_data['scheduled_for']
        if value <= timezone.now():
            raise forms.ValidationError('Choose a future session.')
        return value

class PreferencesForm(forms.ModelForm):
    daily_minutes = forms.IntegerField(min_value=5, max_value=120, label='Minutes available per session')
    class Meta:
        model = Journey
        fields = ['daily_minutes', 'learning_goal']
