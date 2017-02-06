from django.contrib import admin

from listener.models import LavaListener

class LavaListenerAdmin(admin.ModelAdmin):
    pass

admin.site.register(LavaListener, LavaListenerAdmin)
