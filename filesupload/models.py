from django.db import models
from datetime import datetime


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


class Delta(models.Model):
    """

    """
    code_agence = models.CharField(max_length=20)
    num_compte = models.CharField(max_length=11)
    montant = models.IntegerField()

    interet_debiteur_1 = models.IntegerField()
    interet_debiteur_2 = models.IntegerField()
    taxe_interet_debiteur_1 = models.FloatField()
    taxe_interet_debiteur_2 = models.FloatField()

    taux_commission_mvt = models.FloatField()
    taux_commission_dec = models.FloatField()
    commission_mvt = models.IntegerField()
    commission_dec = models.IntegerField()

    frais_fixe = models.IntegerField()
    tva = models.IntegerField()
    taux_tva = models.FloatField()

    net_debit = models.IntegerField()
    solde_agios = models.IntegerField()

    type_account = models.CharField(max_length=10, default="Courant")

    date_deb_arrete = models.DateTimeField()
    date_fin_arrete = models.DateTimeField()
    date_deb_autorisation = models.DateTimeField()
    date_fin_autorisation = models.DateTimeField()
    date_ajout = models.DateTimeField(default=datetime.now)

    class Meta:
        unique_together = ('num_compte', 'date_deb_arrete', 'date_fin_arrete', 'date_deb_autorisation', 'date_fin_autorisation')


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
    # type_account = models.CharField(max_length=2, default='E')


class Operation(models.Model):
    code_operation = models.CharField(max_length=5, unique=True)