from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.views.generic.edit import UpdateView

from ..forms import ProfileForm
from ..models import Profile


class PreferenceView(UpdateView):
    template_name = "tracker/preferences.html"
    model = Profile
    form_class = ProfileForm
    success_url = reverse_lazy("preferences")

    def get_object(self, queryset=None):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile


preference_view = login_required(PreferenceView.as_view())
