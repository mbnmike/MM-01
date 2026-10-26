from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

INPUT_CLASSES = (
    "block w-full rounded-none border border-neutral-300 bg-white px-3 py-2.5 text-sm text-ink "
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


class LoginForm(StyledFormMixin, AuthenticationForm):
    pass


class RegisterForm(StyledFormMixin, UserCreationForm):
    email = forms.EmailField()
    first_name = forms.CharField(label="Name", max_length=150, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email
