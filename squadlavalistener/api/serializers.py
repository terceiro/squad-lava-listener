from rest_framework import serializers

from api.models import Pattern

class PatternSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pattern
        fields = ('lava_server',
            'lava_job_id',
            'lava_job_status',
            'requester',
            'build_job_name',
            'build_job_url',
            'created_at',
            'is_active')
