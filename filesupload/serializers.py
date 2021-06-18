from rest_framework import serializers
from .models import Historique, Compte, Operation


class HistoriqueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Historique
        fields = ['num_compte', 'intitule_compte', 'code_operation']


class CompteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Compte
        fields = '__all__'


class OperationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Operation
        fields = '__all__'