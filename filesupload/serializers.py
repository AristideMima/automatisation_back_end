from rest_framework import serializers
from .models import Historic,  Echelle, Results, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'


class HistoricSerializer(serializers.ModelSerializer):
    class Meta:
        model = Historic
        fields = '__all__'


# class CompteSerializer(serializers.ModelSerializer):
#
#     class Meta:
#         model = Compte
#         fields = '__all__'
#
#
# class OperationSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Operation
#         fields = '__all__'


class EchelleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Echelle
        fields = '___all__'


class ResultsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Results
        fields = '___all__'