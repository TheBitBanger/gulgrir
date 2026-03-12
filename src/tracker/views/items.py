from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic.edit import CreateView
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
