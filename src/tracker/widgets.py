from django.forms.widgets import DateInput


class FlatpickrISODateInput(DateInput):
    input_type = "text"
    format = "%Y-%m-%d"

    def render(self, name, value, attrs=None, renderer=None):
        attrs = attrs or {}
        # add a CSS class the init script will look for
        attrs["class"] = (attrs.get("class", "") + " js-date").strip()

        return super().render(name, value, attrs, renderer)
