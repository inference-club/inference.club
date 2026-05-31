from django.urls import path

from .openai_views import (
    AudioTranscriptionsView,
    ChatCompletionsView,
    CompletionsView,
    ModelsView,
)

app_name = "openai"

urlpatterns = [
    path("models", ModelsView.as_view(), name="models"),
    path("models/", ModelsView.as_view()),
    path("chat/completions", ChatCompletionsView.as_view(), name="chat-completions"),
    path("chat/completions/", ChatCompletionsView.as_view()),
    path("completions", CompletionsView.as_view(), name="completions"),
    path("completions/", CompletionsView.as_view()),
    path("audio/transcriptions", AudioTranscriptionsView.as_view(), name="audio-transcriptions"),
    path("audio/transcriptions/", AudioTranscriptionsView.as_view()),
]
