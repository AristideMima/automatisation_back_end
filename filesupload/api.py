from rest_framework import viewsets
from .models import Historique, Compte, Operation
from .serializers import HistoriqueSerializer, CompteSerializer, OperationSerializer


# Historique viewset


class HistoriqueView(viewsets.ModelViewSet):
    queryset = Historique.objects.all()
    serializer_class = HistoriqueSerializer


class CompteView(viewsets.ModelViewSet):
    queryset = Compte.objects.all()
    serializer_class = CompteSerializer


class OperationView(viewsets.ModelViewSet):
    queryset = Operation.objects.all()
    serializer_class = OperationSerializer
