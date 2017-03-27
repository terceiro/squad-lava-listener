from django.contrib import admin

from api.models import Pattern, SquadToken, Submission
from api.tasks import submit_to_lava, check_job_status


def check_status(modeladmin, request, queryset):
    for pattern in queryset:
        check_job_status.delay(pattern, {
            'job': pattern.lava_job_id,
            'description': 'something',
            'status': "Submitted",
            'pipeline': True,
        })
check_status.short_description = 'Check LAVA for test status and results'


class PatternAdmin(admin.ModelAdmin):
    actions = [check_status]
    list_filter = ('is_active', 'lava_job_status', 'requester')


class SquadTokenAdmin(admin.ModelAdmin):
    pass


def submit(modeladmin, request, queryset):
    for submission in queryset:
        submit_to_lava.delay(submission.id)
submit.short_description = 'Submit to LAVA'

class SubmissionAdmin(admin.ModelAdmin):
    actions = [submit]
    list_filter = ('submitted', 'requester')


admin.site.register(Pattern, PatternAdmin)
admin.site.register(SquadToken, SquadTokenAdmin)
admin.site.register(Submission, SubmissionAdmin)
