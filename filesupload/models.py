from django.db import models


# Create your models here.

class Historique(models.Model):
    """

    """
    id = models.AutoField(primary_key=True)
    code_agence = models.CharField(max_length=20)
    date_comptable = models.DateTimeField()
    date_valeur = models.DateTimeField()
    num_compte = models.CharField(max_length=11)
    intitule_compte = models.CharField(max_length=100)
    libelle_operation = models.CharField(max_length=100)
    code_operation = models.CharField(max_length=5)
    sens = models.CharField(max_length=2)
    montant = models.IntegerField()


class Arretes(models.Model):
    """

    """
    code_agence = models.CharField(max_length=20)
    num_compte = models.CharField(max_length=11)
    montant = models.IntegerField()
    date_deb_arrete = models.DateTimeField()
    date_fin_arrete = models.DateTimeField()
    date_deb_autorisation = models.DateTimeField()
    date_fin_autorisation = models.DateTimeField()
    
    class Meta:
        unique_together = ('num_compte', 'date_deb_arrete', 'date_fin_arrete', 'date_deb_autorisation', 'date_fin_autorisation')


class Compte(models.Model):
    """

    """
    num_compte = models.CharField(max_length=11, primary_key=True)
    intitule_compte = models.CharField(max_length=100)
    type_account = models.CharField(max_length=2, default='E')


class Operation(models.Model):
    code_operation = models.CharField(max_length=5, unique=True)