from django import forms

from .models import Subscriber

INPUT_CLASSES = (
    "field-input block w-full rounded-none border border-neutral-300 bg-white px-3 py-2.5 text-sm text-ink "
    "placeholder:text-neutral-400 focus:border-ink focus:outline-none focus:ring-1 focus:ring-ink"
)


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.RadioSelect, forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                continue
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {INPUT_CLASSES}".strip()


class ContactForm(StyledFormMixin, forms.Form):
    name = forms.CharField(max_length=120)
    email = forms.EmailField()
    order_number = forms.CharField(label="Order # (if any)", max_length=20, required=False)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 6}))


class SubscribeForm(forms.Form):
    email = forms.EmailField(max_length=254)
    source = forms.ChoiceField(choices=Subscriber.Source.choices, required=False)
    website = forms.CharField(required=False)  # honeypot: people never see it, bots fill it
