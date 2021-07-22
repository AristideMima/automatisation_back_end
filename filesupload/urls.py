from rest_framework import routers
from .api import *
from .views import make_calcul, get_infos
from django.urls import include, path


router = routers.DefaultRouter()
router.register('api/historiques', HistoriqueView, 'historiques')
router.register('api/comptes', CompteView, 'comptes')
router.register('api/operations', OperationView, 'operations')

urlpatterns = [
    path('', include(router.urls)),
    path('api/calculs', make_calcul),
    path('api/getInfos', get_infos),
]
