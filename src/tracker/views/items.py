from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django.views.generic.list import ListView

from ..models import Item


class ItemCreate(LoginRequiredMixin, CreateView):
    model = Item
    fields = ["media_type", "title"]
    template_name = "tracker/form.html"
    success_url = reverse_lazy("item_list")
    extra_context = {"model_verbose": Item._meta.verbose_name}


class ItemList(LoginRequiredMixin, ListView):
    model = Item
    template_name = "tracker/item_list.html"
    paginate_by = 30

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(usage_count=Count("useritem"))
            .order_by("title")
        )


class ItemUpdate(LoginRequiredMixin, UpdateView):
    model = Item
    fields = ["media_type", "title"]
    template_name = "tracker/form.html"
    success_url = reverse_lazy("item_list")
    extra_context = {"model_verbose": Item._meta.verbose_name}


class ItemDelete(LoginRequiredMixin, DeleteView):
    model = Item
    template_name = "tracker/confirm_delete.html"
    success_url = reverse_lazy("item_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["usage_count"] = self.object.useritem_set.count()
        ctx["usage_subject"] = "global item"
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.useritem_set.exists():
            messages.error(
                request,
                "This global item is in use and cannot be deleted.",
            )
            return redirect("item_list")
        return super().post(request, *args, **kwargs)
