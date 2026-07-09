from django.urls import path

from . import views

urlpatterns = [
    # Public build/version metadata (frontend version indicator).
    path("meta/", views.meta, name="meta"),
]
