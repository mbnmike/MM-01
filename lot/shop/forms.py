from django import forms

from core.forms import StyledFormMixin

from .models import ShippingMethod

COUNTRIES = [
    ("US", "United States"),
    ("CA", "Canada"),
    ("GB", "United Kingdom"),
    ("AU", "Australia"),
    ("JP", "Japan"),
    ("DE", "Germany"),
    ("FR", "France"),
    ("NL", "Netherlands"),
    ("NZ", "New Zealand"),
]


class ShippingChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.name


class CheckoutForm(StyledFormMixin, forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    full_name = forms.CharField(max_length=120, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    phone = forms.CharField(max_length=40, required=False, widget=forms.TextInput(attrs={"autocomplete": "tel"}))
    address_line1 = forms.CharField(
        label="Address", max_length=200, widget=forms.TextInput(attrs={"autocomplete": "address-line1"})
    )
    address_line2 = forms.CharField(
        label="Apt / suite",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "address-line2"}),
    )
    city = forms.CharField(max_length=100, widget=forms.TextInput(attrs={"autocomplete": "address-level2"}))
    region = forms.CharField(
        label="State / region",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "address-level1"}),
    )
    postal_code = forms.CharField(
        label="Postal code", max_length=20, widget=forms.TextInput(attrs={"autocomplete": "postal-code"})
    )
    country = forms.ChoiceField(choices=COUNTRIES, initial="US")
    shipping_method = ShippingChoiceField(
        queryset=ShippingMethod.objects.filter(is_active=True),
        widget=forms.RadioSelect,
        empty_label=None,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        first = self.fields["shipping_method"].queryset.first()
        if first and not self.initial.get("shipping_method"):
            self.initial["shipping_method"] = first.pk
