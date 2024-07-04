from django.urls import path

from . import views

urlpatterns = [
  path("", views.index, name="index"),
  path("search-mp", views.search_mp, name="search_mp"),
  path("chat-with/<mp_name>", views.chat_with, name="chat_with"),
  path("chat-with/<mp_name>/message", views.message, name="chat_with"),
  path("about", views.about, name="about"),
]

