from django.contrib import admin

from api.models import Pattern, SquadToken, Submission
from api.tasks import submit_to_lava


class PatternAdmin(admin.ModelAdmin):
    pass


class SquadTokenAdmin(admin.ModelAdmin):
    pass


def submit(modeladmin, request, queryset):
    for submission in queryset:
        submit_to_lava.delay(submission.id)
submit.short_description = 'Submit to LAVA'

class SubmissionAdmin(admin.ModelAdmin):
    actions = [submit]


admin.site.register(Pattern, PatternAdmin)
admin.site.register(SquadToken, SquadTokenAdmin)
admin.site.register(Submission, SubmissionAdmin)
