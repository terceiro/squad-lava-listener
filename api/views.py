from django.shortcuts import render

from rest_framework import response
from rest_framework import status
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, DjangoModelPermissions

from api.models import Pattern, Submission
from api.serializers import PatternSerializer, SubmissionSerializer
from api.tasks import submit_to_lava

class PatternViewSet(viewsets.ModelViewSet):
    permission_classes = [DjangoModelPermissions]
    queryset = Pattern.objects.all().order_by('lava_job_id')
    serializer_class = PatternSerializer
    pagination_class = None

    def create(self, request, *args, **kwargs):
        request.data.update({"requester": request.user.pk})
        serializer = PatternSerializer(data=request.data)
        is_valid = serializer.is_valid()
        if len(Pattern.objects.filter(lava_job_id=request.data['lava_job_id'])) > 0:
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        if is_valid:
            serializer.save()
            return response.Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return response.Response("{}", status=status.HTTP_401_UNAUTHORIZED)

class SubmissionViewSet(viewsets.ModelViewSet):
    permission_classes = [DjangoModelPermissions]
    serializer_class = SubmissionSerializer
    queryset = Submission.objects.all()

    def create(self, request, *args, **kwargs):
        request.data.update({"requester": request.user.pk})
        return super(SubmissionViewSet, self).create(request, *args, **kwargs)

    def perform_create(self, serializer):
        submission = serializer.save()
        submit_to_lava.delay(submission.id)
