import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError
from django.db.models import Count
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django.views.generic.list import ListView

from ..forms import TagForm
from ..models import Tag
from .mixins import OwnObjectsMixin


class TagCreate(LoginRequiredMixin, CreateView):
    model = Tag
    form_class = TagForm
    template_name = "tracker/form.html"
    success_url = reverse_lazy("tag_list")
    extra_context = {"model_verbose": Tag._meta.verbose_name}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user

        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class TagList(OwnObjectsMixin, ListView):
    model = Tag
    template_name = "tracker/tag_list.html"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(usage_count=Count("user_items"))
            .order_by("name")
        )


class TagUpdate(OwnObjectsMixin, UpdateView):
    model = Tag
    form_class = TagForm
    template_name = "tracker/form.html"
    success_url = reverse_lazy("tag_list")
    extra_context = {"model_verbose": Tag._meta.verbose_name}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user

        return kwargs


class TagDelete(OwnObjectsMixin, DeleteView):
    model = Tag
    template_name = "tracker/confirm_delete.html"
    success_url = reverse_lazy("tag_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["usage_count"] = self.object.user_items.count()
        ctx["usage_subject"] = "tag"

        return ctx


@method_decorator(csrf_protect, name="dispatch")
class TagQuickCreate(LoginRequiredMixin, View):
    def post(self, request):
        name = ""
        ctype = request.headers.get("Content-Type", "")
        try:
            if "application/json" in ctype:
                payload = json.loads(request.body.decode("utf-8") or "{}")
                name = (payload.get("name") or "").strip()
            else:
                name = (request.POST.get("name") or "").strip()
        except Exception:
            return JsonResponse({"error": "Invalid request"}, status=400)

        if not name:
            return JsonResponse({"error": "Tag name cannot be empty"}, status=400)
        if len(name) > 64:
            return JsonResponse({"error": "Tag name too long (max 64)"}, status=400)

        existing = Tag.objects.filter(user=request.user, name__iexact=name).first()
        if existing:
            return JsonResponse({"id": existing.id, "name": existing.name})

        try:
            tag = Tag.objects.create(user=request.user, name=name)
            return JsonResponse({"id": tag.id, "name": tag.name})
        except IntegrityError:
            existing = Tag.objects.filter(user=request.user, name__iexact=name).first()
            if existing:
                return JsonResponse({"id": existing.id, "name": existing.name})
            return JsonResponse({"error": "Could not create tag"}, status=400)
