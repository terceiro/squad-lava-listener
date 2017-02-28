from django.contrib import admin

from api.models import Pattern, SquadToken


class PatternAdmin(admin.ModelAdmin):
    pass


class SquadTokenAdmin(admin.ModelAdmin):
    pass


admin.site.register(Pattern, PatternAdmin)
admin.site.register(SquadToken, SquadTokenAdmin)
