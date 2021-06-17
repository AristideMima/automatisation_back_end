from rest_framework import serializers
from .models import Historique


class HistoriqueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Historique
        fields = ['num_compte', 'intitule_compte', 'code_operation']
