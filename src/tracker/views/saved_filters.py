from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic.edit import DeleteView, UpdateView
from django.views.generic.list import ListView

from ..forms import UserItemFilterForm
from ..models import SavedFilter
from .mixins import OwnObjectsMixin


class SavedFilterList(OwnObjectsMixin, ListView):
    model = SavedFilter
    template_name = "tracker/saved_filter_list.html"


class SavedFilterUpdate(OwnObjectsMixin, UpdateView):
    model = SavedFilter
    fields = ["name"]
    template_name = "tracker/form.html"
    success_url = reverse_lazy("saved_filter_list")
    extra_context = {"model_verbose": SavedFilter._meta.verbose_name}


class SavedFilterDelete(OwnObjectsMixin, DeleteView):
    model = SavedFilter
    template_name = "tracker/confirm_delete.html"
    success_url = reverse_lazy("saved_filter_list")


@require_POST
@login_required
def save_current_filter(request):
    form = UserItemFilterForm(request.POST, user=request.user)
    if not form.is_valid():
        return HttpResponseBadRequest("Invalid filter")

    name = (request.POST.get("filter_name") or "Unnamed").strip()
    definition = form.to_definition()
    active_filter_id = request.POST.get("active_filter_id")
    active_filter_name = request.POST.get("active_filter_name")

    if active_filter_id and active_filter_name and name == active_filter_name:
        sf = get_object_or_404(SavedFilter, pk=active_filter_id, user=request.user)
        sf.definition = definition
        sf.name = name
        sf.save()
    else:
        existing = SavedFilter.objects.filter(user=request.user, name=name).first()
        if existing:
            if request.POST.get("overwrite_existing") == "1":
                existing.definition = definition
                existing.save()
                sf = existing
            else:
                return HttpResponse(
                    "A saved filter with this name already exists. Update it instead?",
                    status=409,
                )
        else:
            sf = SavedFilter.objects.create(
                user=request.user,
                name=name,
                definition=definition,
            )

    url = f"{reverse('useritem_dashboard')}?{sf.query_params()}"
    resp = HttpResponse("")
    resp["HX-Redirect"] = url

    return resp
