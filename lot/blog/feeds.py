from django.conf import settings
from django.contrib.syndication.views import Feed
from django.urls import reverse_lazy

from .models import BlogSettings, Post


class LatestPostsFeed(Feed):
    link = reverse_lazy("blog:list")

    def title(self):
        return f"Articles — {settings.BRAND['name']}"

    def description(self):
        return BlogSettings.load().intro

    def items(self):
        return Post.objects.published().select_related("author", "category")[:20]

    def item_title(self, item):
        return item.display_title

    def item_description(self, item):
        return item.summary

    def item_pubdate(self, item):
        return item.published_at

    def item_author_name(self, item):
        return item.author_name
