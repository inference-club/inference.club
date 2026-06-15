"""Serializers for the Narration Studio (PRD 12 §5.4): Episodes, their ordered
Segments, and each Segment's takes (Variants). Audio is surfaced as browser URLs
off the linked ``MediaAsset`` (the same ``asset_url`` helper the rest of the app
uses), never as raw paths."""
from rest_framework import serializers

from .models import Episode, Segment, Variant
from .serializers import asset_url


class VariantSerializer(serializers.ModelSerializer):
    """One take of a segment: its audio, duration, word timestamps, and the
    StudioVoice-cleaned copy (kept beside the original)."""

    audio_url = serializers.SerializerMethodField()
    cleaned_audio_url = serializers.SerializerMethodField()

    class Meta:
        model = Variant
        fields = [
            "id", "text", "duration_seconds", "words",
            "audio_url", "cleaned_audio_url", "clean_status",
            "inference_request_id", "created_on",
        ]

    def get_audio_url(self, obj):
        return asset_url(obj.audio, self.context.get("request")) if obj.audio_id else None

    def get_cleaned_audio_url(self, obj):
        if not obj.cleaned_audio_id:
            return None
        return asset_url(obj.cleaned_audio, self.context.get("request"))


class SegmentSerializer(serializers.ModelSerializer):
    """A narration unit + all its takes. ``selected_variant_id`` is the active
    take used for playback/export."""

    variants = VariantSerializer(many=True, read_only=True)
    voice_sample_name = serializers.SerializerMethodField()

    class Meta:
        model = Segment
        fields = [
            "id", "position", "text", "original_text", "status",
            "selected_variant_id", "voice_sample_id", "voice_sample_name",
            "variants", "created_on", "modified_on",
        ]

    def get_voice_sample_name(self, obj):
        return obj.voice_sample.speaker_name if obj.voice_sample_id else None


class EpisodeListSerializer(serializers.ModelSerializer):
    """Slim episode row for the Studio library (no segments)."""

    segment_count = serializers.IntegerField(source="segments.count", read_only=True)

    class Meta:
        model = Episode
        fields = [
            "id", "title", "description", "workflow_run_id",
            "segment_count", "created_on", "modified_on",
        ]


class EpisodeSerializer(EpisodeListSerializer):
    """Full episode with its ordered segments (the Studio workspace payload)."""

    segments = SegmentSerializer(many=True, read_only=True)

    class Meta(EpisodeListSerializer.Meta):
        fields = EpisodeListSerializer.Meta.fields + ["segments"]
