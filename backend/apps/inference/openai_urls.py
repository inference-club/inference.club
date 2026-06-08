from django.urls import path

from .openai_views import (
    AudioSpeechView,
    AudioTranscriptionsView,
    AudioVoicesView,
    ChatCompletionsView,
    CompletionsView,
    ImageEditsView,
    ImageGenerationsView,
    Mesh3DGenerationsView,
    ModelsView,
    MusicGenerationsView,
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
    path("audio/speech", AudioSpeechView.as_view(), name="audio-speech"),
    path("audio/speech/", AudioSpeechView.as_view()),
    path("audio/voices", AudioVoicesView.as_view(), name="audio-voices"),
    path("audio/voices/", AudioVoicesView.as_view()),
    path("images/generations", ImageGenerationsView.as_view(), name="images-generations"),
    path("images/generations/", ImageGenerationsView.as_view()),
    path("images/edits", ImageEditsView.as_view(), name="images-edits"),
    path("images/edits/", ImageEditsView.as_view()),
    path("3d/generations", Mesh3DGenerationsView.as_view(), name="mesh-generations"),
    path("3d/generations/", Mesh3DGenerationsView.as_view()),
    path("music/generations", MusicGenerationsView.as_view(), name="music-generations"),
    path("music/generations/", MusicGenerationsView.as_view()),
]
