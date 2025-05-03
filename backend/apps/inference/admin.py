from django.contrib import admin
from .models import InferenceRequest


@admin.register(InferenceRequest)
class InferenceRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "inference_type", "status", "created_on")
    list_filter = ("inference_type", "status", "created_on")
    readonly_fields = ("created_on", "modified_on")
    search_fields = ("user__username", "payload")
