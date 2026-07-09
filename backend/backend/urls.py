"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import include, path

from apps.core.views import healthz, readyz
from apps.inference.views import OpenAPISchemaView

urlpatterns = [
    # Liveness + readiness probes (k8s). Unauthenticated, mounted at the root
    # so they're reachable without the /api prefix. healthz = process up (no
    # I/O); readyz = dependencies (DB) reachable.
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    path("admin/", admin.site.urls),
    path("oauth/", include("social_django.urls", namespace="social")),
    path("v1/", include("apps.inference.openai_urls", namespace="openai")),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.accounts.urls")),
    path("api/inference/", include("apps.inference.urls")),
    path("api/admin/", include("apps.inference.staff_urls")),
    path("api/admin/", include("apps.accounts.staff_urls")),
    # Public OpenAPI spec for the OpenAI-compatible /v1 API (powers the docs
    # page and is importable by external tools).
    path("openapi.json", OpenAPISchemaView.as_view(), name="openapi-json"),
    path("openapi.yaml", OpenAPISchemaView.as_view(as_yaml=True), name="openapi-yaml"),
]
