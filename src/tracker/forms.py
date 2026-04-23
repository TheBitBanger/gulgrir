from typing import Any

from django import forms

from .models import Item, Profile, Tag, UserItem, UserItemHistory
from .widgets import FlatpickrISODateInput


class UserItemForm(forms.ModelForm):
    completed_at = forms.DateTimeField(
        required=False,
        widget=FlatpickrISODateInput(),
        label="Completed at (optional)",
    )
    revisited_at = forms.DateTimeField(
        required=False,
        widget=FlatpickrISODateInput(),
        label="Revisited at (optional)",
    )

    class Meta:
        model = UserItem
        fields = [
            "item",
            "is_project",
            "is_endless",
            "title_override",
            "shelf",
            "tier",
            "tags",
        ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Scope tags to current user
        if user is not None and "tags" in self.fields:
            self.fields["tags"].queryset = Tag.objects.filter(user=user).order_by(
                "name"
            )

        # Light Tailwind-ish styling for consistent sizing
        base = "w-full rounded-lg border px-3 py-2 text-sm"
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                if name in {"is_project", "is_endless"}:
                    field.widget.attrs.setdefault("class", "pill-toggle__input")
                else:
                    field.widget.attrs.setdefault("class", "h-4 w-4")
                continue
            if isinstance(field.widget, forms.Select | forms.SelectMultiple):
                field.widget.attrs.setdefault("class", base)
            else:
                field.widget.attrs.setdefault("class", base)

    def save(self, commit=True):
        ui = super().save(commit=False)
        if commit:
            cd = self.cleaned_data
            if cd["completed_at"]:
                ui.is_redoing = False
            ui.save()
            self.save_m2m()

            # create history rows if the optional dates were supplied
            if cd["completed_at"]:
                UserItemHistory.objects.create(
                    user_item=ui,
                    event_type=UserItemHistory.Event.COMPLETED,
                    happened_at=cd["completed_at"],
                )
            if cd["revisited_at"]:
                UserItemHistory.objects.create(
                    user_item=ui,
                    event_type=UserItemHistory.Event.REVISITED,
                    happened_at=cd["revisited_at"],
                )
        return ui


PRESETS = [
    ("%d/%m/%Y", "19/05/2025 (DD/MM/YYYY)"),
    ("%m/%d/%Y", "05/19/2025 (MM/DD/YYYY)"),
    ("%Y-%m-%d", "2025-05-19 (ISO)"),
]


class ProfileForm(forms.ModelForm):
    date_format = forms.ChoiceField(choices=PRESETS, label="Preferred date format")
    theme = forms.ChoiceField(
        choices=Profile.Theme.choices,
        label="Theme",
    )

    class Meta:
        model = Profile
        fields = ["date_format", "timezone", "theme"]


class UserItemFilterForm(forms.Form):
    shelf = forms.MultipleChoiceField(
        required=False,
        choices=UserItem.Shelf.choices,
        widget=forms.CheckboxSelectMultiple,
        label="Shelf",
    )
    media_type = forms.MultipleChoiceField(
        required=False,
        choices=Item.MediaType.choices,
        widget=forms.CheckboxSelectMultiple,
        label="Media Type",
    )
    is_project = forms.BooleanField(required=False, label="Projects Only")
    tags = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Tag.objects.none(),  # overwritten in __init__
        widget=forms.CheckboxSelectMultiple,
    )
    title_icontains = forms.CharField(
        required=False,
        label="Title Contains",
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["tags"].queryset = Tag.objects.filter(user=user)
        self.fields["tags"].widget = forms.CheckboxSelectMultiple()
        self.fields["tags"].help_text = ""
        self.fields["title_icontains"].widget.attrs.setdefault(
            "class",
            "control",
        )

    def to_definition(self):
        """
        Return a compact dict (JSON-serialisable) with only
        the fields the user actually set.
        """
        cd = self.cleaned_data
        d: dict[str, Any] = {}

        if cd["shelf"]:
            d["shelf"] = cd["shelf"]  # list[str]

        if cd["media_type"]:
            d["media_type"] = cd["media_type"]  # list[str]

        if cd["is_project"]:
            d["is_project"] = True  # bool

        if cd["title_icontains"]:
            d["title_icontains"] = cd["title_icontains"]  # str

        if cd["tags"]:  # QuerySet[Tag]
            d["tags"] = [tag.pk for tag in cd["tags"]]  # list[int]

        return d


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        base = "w-full rounded-lg border px-3 py-2 text-sm"
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", base)

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            return name

        if self.user is None:
            return name

        exists = (
            Tag.objects.filter(user=self.user, name__iexact=name)
            .exclude(pk=self.instance.pk)
            .exists()
        )
        if exists:
            raise forms.ValidationError("You already have a tag with this name.")

        return name
