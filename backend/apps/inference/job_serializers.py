"""Serializers for the async job / batch / workflow API (PRD 10).

A "job" is an InferenceRequest, so the job serializer extends the existing list
serializer — it already exposes every media url (image/audio/video/mesh) the
queue page and the DAG viewer need — and just adds the queue/lifecycle fields.
"""
from rest_framework import serializers

from .models import Batch, InferenceRequest, WorkflowRun, WorkflowStepRun
from .serializers import InferenceRequestListSerializer


class JobSerializer(InferenceRequestListSerializer):
    """An async job: the rich request card + its queue lifecycle fields."""

    batch_id = serializers.IntegerField(read_only=True)
    step_run_id = serializers.IntegerField(read_only=True)

    class Meta(InferenceRequestListSerializer.Meta):
        fields = InferenceRequestListSerializer.Meta.fields + [
            "is_async",
            "queued_at",
            "started_at",
            "finished_at",
            "run_after",
            "attempts",
            "max_attempts",
            "priority",
            "error",
            "batch_id",
            "step_run_id",
        ]


class WorkflowStepRunSerializer(serializers.ModelSerializer):
    """One DAG node + the jobs it spawned (with their media), so the viewer can
    render thumbnails as steps complete."""

    jobs = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowStepRun
        fields = [
            "id",
            "step_id",
            "kind",
            "title",
            "depends_on",
            "status",
            "output",
            "error",
            "position",
            "started_at",
            "finished_at",
            "jobs",
        ]

    def get_jobs(self, obj):
        qs = obj.jobs.all().order_by("id")
        return JobSerializer(qs, many=True, context=self.context).data


class WorkflowRunSerializer(serializers.ModelSerializer):
    """A workflow run for the DAG viewer: status, the steps (nodes), and the
    edges (derived from each step's depends_on)."""

    steps = WorkflowStepRunSerializer(many=True, read_only=True)
    edges = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowRun
        fields = [
            "id",
            "name",
            "status",
            "inputs",
            "error",
            "created_on",
            "started_at",
            "finished_at",
            "steps",
            "edges",
        ]

    def get_edges(self, obj):
        edges = []
        for step in obj.steps.all():
            for dep in step.depends_on or []:
                edges.append({"from": dep, "to": step.step_id})
        return edges


class WorkflowRunListSerializer(serializers.ModelSerializer):
    """Slim run summary for the runs list (no per-step payloads)."""

    step_count = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowRun
        fields = [
            "id",
            "name",
            "status",
            "created_on",
            "started_at",
            "finished_at",
            "step_count",
        ]

    def get_step_count(self, obj):
        return obj.steps.count()


class BatchSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    jobs = serializers.SerializerMethodField()
    counts = serializers.SerializerMethodField()

    class Meta:
        model = Batch
        fields = ["id", "label", "status", "counts", "created_on", "jobs"]

    def get_status(self, obj):
        return obj.aggregate_status()

    def get_jobs(self, obj):
        qs = obj.jobs.all().order_by("id")
        return JobSerializer(qs, many=True, context=self.context).data

    def get_counts(self, obj):
        counts = {}
        for s in obj.jobs.values_list("status", flat=True):
            counts[s] = counts.get(s, 0) + 1
        return counts
