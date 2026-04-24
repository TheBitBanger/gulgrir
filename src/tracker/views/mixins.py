from typing import Any, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest


class OwnObjectsMixin(LoginRequiredMixin):
    """Mix-in that restricts queryset to the logged-in user."""

    request: HttpRequest

    def get_queryset(self) -> QuerySet[Any]:
        super_obj: Any = super()
        queryset = cast(QuerySet[Any], super_obj.get_queryset())
        return queryset.filter(user=self.request.user)
