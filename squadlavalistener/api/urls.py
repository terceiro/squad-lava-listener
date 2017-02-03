from django.conf.urls import include, url

from rest_framework import routers

from . import views

router = routers.DefaultRouter()
router.register('pattern', views.PatternViewSet)

urlpatterns = [
        url(r'^', include(router.urls)),
]
