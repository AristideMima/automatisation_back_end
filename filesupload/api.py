from rest_framework import viewsets
from .models import *
from .serializers import *
from rest_framework.permissions import IsAuthenticated


# Historique viewset


class HistoriqueView(viewsets.ModelViewSet):

    permission_classes = [IsAuthenticated]

    serializer_class = HistoricSerializer

    def get_queryset(self):
        return self.request.user.historics


# class CompteView(viewsets.ModelViewSet):
#
#     permission_classes = [IsAuthenticated]
#
#     queryset = Compte.objects.all()
#     serializer_class = CompteSerializer
#
#
# class OperationView(viewsets.ModelViewSet):
#
#     permission_classes = [IsAuthenticated]
#     queryset = Operation.objects.all()
#     serializer_class = OperationSerializer


class EchelleView(viewsets.ModelViewSet):

    permission_classes = [IsAuthenticated]
    serializer_class = EchelleSerializer

    def get_queryset(self):
        return self.request.user.echelles


class ResultView(viewsets.ModelViewSet):

    permission_classes = [IsAuthenticated]
    serializer_class = ResultsSerializer

    def get_queryset(self):
        return self.request.user.results