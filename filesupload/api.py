from rest_framework import viewsets
from .models import Historique
from .serializers import HistoriqueSerializer

# Historique viewset
class HistoriqueView(viewsets.ModelViewSet):

    queryset = Historique.objects.all()
    serializer_class = HistoriqueSerializer