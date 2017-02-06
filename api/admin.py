from django.contrib import admin

from api.models import Pattern

# Register your models here.
class PatternAdmin(admin.ModelAdmin):
    pass

admin.site.register(Pattern, PatternAdmin)
