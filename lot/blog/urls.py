from django.urls import path

from . import views
from .feeds import LatestPostsFeed

app_name = "blog"

urlpatterns = [
    path("", views.post_list, name="list"),
    path("feed/", LatestPostsFeed(), name="feed"),
    path("<int:year>/<int:month>/", views.post_list, name="month"),
    path("tag/<slug:tag_slug>/", views.post_list, name="tag"),
    path("<slug:slug>/", views.post_detail, name="post"),
    path("<slug:slug>/comment/", views.post_comment, name="comment"),
]
