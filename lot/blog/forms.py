import re
import time

from django import forms
from django.core import signing

from core.forms import StyledFormMixin

from .models import Post

TOKEN_SALT = "blog.comment"
MIN_SECONDS = 3
MAX_AGE = 2 * 24 * 3600
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")


def comment_token(post):
    return signing.dumps({"p": post.pk, "t": int(time.time())}, salt=TOKEN_SALT)


class CommentForm(StyledFormMixin, forms.Form):
    name = forms.CharField(label="Display name", max_length=60, required=False,
                           widget=forms.TextInput(attrs={"autocomplete": "nickname"}))
    email = forms.EmailField(max_length=254, help_text="Never shown publicly.",
                             widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    body = forms.CharField(label="Comment", min_length=2, max_length=3000,
                           widget=forms.Textarea(attrs={"rows": 5, "maxlength": 3000}))
    # Honeypot: hidden from people, irresistible to bots.
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    def __init__(self, *args, post, **kwargs):
        self.post = post
        self.is_trap = False
        super().__init__(*args, **kwargs)

    def clean_name(self):
        return re.sub(r"\s+", " ", CONTROL_CHARS.sub("", self.cleaned_data["name"])).strip()

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_body(self):
        body = CONTROL_CHARS.sub("", self.cleaned_data["body"].replace("\r\n", "\n"))
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        if len(body) < 2:
            raise forms.ValidationError("Please write a comment.")
        return body

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("website"):
            self.is_trap = True
            return cleaned
        try:
            data = signing.loads(self.data.get("token", ""), salt=TOKEN_SALT, max_age=MAX_AGE)
        except signing.SignatureExpired:
            raise forms.ValidationError("This page was open a long time, so the form expired. Please submit again.")
        except signing.BadSignature:
            raise forms.ValidationError("Something went wrong with the form. Please reload the page and try again.")
        if data.get("p") != self.post.pk:
            raise forms.ValidationError("Something went wrong with the form. Please reload the page and try again.")
        if time.time() - data.get("t", 0) < MIN_SECONDS:
            raise forms.ValidationError("That was quick! Please wait a few seconds and submit again.")
        return cleaned


class PostAdminForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = "__all__"
        widgets = {
            "title": forms.TextInput(attrs={"class": "lot-title-input", "placeholder": "Post title", "autocomplete": "off"}),
            "excerpt": forms.Textarea(attrs={"rows": 2, "class": "lot-excerpt-input", "maxlength": 300,
                                             "placeholder": "A sentence or two that sums up the post (optional)"}),
            "body": forms.Textarea(attrs={"class": "lot-body-input", "spellcheck": "true",
                                          "placeholder": "Start writing… Use the toolbar or Markdown."}),
            "cover_alt": forms.TextInput(attrs={"placeholder": "Describe the photo"}),
            "cover_caption": forms.TextInput(attrs={"placeholder": "Optional caption"}),
            "meta_description": forms.Textarea(attrs={"rows": 3, "maxlength": 160}),
        }
