from django.shortcuts import render
from rest_framework import generics, permissions
from rest_framework.permissions import IsAuthenticated
from .models import InferenceRequest
from .serializers import InferenceRequestSerializer

# Create your views here.


class InferenceRequestView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InferenceRequestSerializer

    def get_queryset(self):
        return InferenceRequest.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class RetrieveInferenceRequestView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InferenceRequestSerializer
    lookup_field = "id"

    def get_queryset(self):
        return InferenceRequest.objects.filter(user=self.request.user)
