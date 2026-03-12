from django.contrib.auth.mixins import LoginRequiredMixin


class OwnObjectsMixin(LoginRequiredMixin):
    """Mix-in that restricts queryset to the logged-in user."""

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)
