from rest_framework import routers
from .api import *
from .views import make_calcul, get_infos, get_files_list, set_active_file, delete_file, get_statistics, compute_files
from django.urls import include, path


router = routers.DefaultRouter()
# router.register('api/historiques', HistoriqueView, 'historiques')
router.register('api/auth', UserView, 'users')
# router.register('api/comptes', CompteView, 'comptes')
# router.register('api/operations', OperationView, 'operations')

urlpatterns = [
    path('', include(router.urls)),
    path('api/calculs', make_calcul),
    path('api/activateFile', get_files_list),
    path('api/setActiveFile', set_active_file),
    path('api/deleteFile', delete_file),
    path('api/getInfos', get_infos),
    path('api/getStats', get_statistics),
    path('api/computeUnique', compute_files),
]
