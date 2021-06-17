from rest_framework import routers
from .api import *
from django.urls import include, path

router = routers.DefaultRouter()
router.register('api/historiques', HistoriqueView, 'historiques')

urlpatterns = [
    path('', include(router.urls)),
]