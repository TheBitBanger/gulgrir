from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.views.generic.edit import UpdateView

from ..forms import FocusGoalSettingsForm, ProfileForm
from ..models import Profile


class PreferenceView(UpdateView):
    template_name = "tracker/preferences.html"
    model = Profile
    form_class = ProfileForm
    success_url = reverse_lazy("preferences")

    def get_object(self, queryset=None):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile


class FocusGoalSettingsView(UpdateView):
    template_name = "tracker/focus_settings.html"
    model = Profile
    form_class = FocusGoalSettingsForm
    success_url = reverse_lazy("focus_settings")

    def get_object(self, queryset=None):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile


preference_view = login_required(PreferenceView.as_view())
focus_goal_settings_view = login_required(FocusGoalSettingsView.as_view())
