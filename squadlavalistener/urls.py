from django.conf.urls import include, url
from django.contrib import admin
from django.urls import reverse
from django.shortcuts import redirect


def goto_admin(request):
    return redirect(reverse('admin:index'))


urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^api/', include('api.urls')),
    url(r'^$', goto_admin),
]
