from django.db import models
from datetime import datetime
from accounts.models import User


class File(models.Model):

    user = models.ForeignKey(User, related_name="files", on_delete=models.CASCADE, null=True)
    file_path = models.TextField()
    file_type = models.CharField(max_length=20)
    active_file =models.BooleanField(default=False)
    date_inf = models.DateField()
    date_sup = models.DateField()
    longueur = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('date_inf', 'date_sup', 'longueur', 'file_type')

# class Historique(models.Model):
#     """
#
#     """
#     id = models.AutoField(primary_key=True)
#     code_agence = models.CharField(max_length=20)
#     date_comptable = models.DateTimeField()
#     date_valeur = models.DateTimeField()
#     num_compte = models.CharField(max_length=11)
#     intitule_compte = models.CharField(max_length=100)
#     libelle_operation = models.CharField(max_length=100)
#     code_operation = models.CharField(max_length=5)
#     sens = models.CharField(max_length=2)
#     montant = models.IntegerField()
#
#
# class Delta(models.Model):
#     """
#
#     """
#     code_agence = models.CharField(max_length=20)
#     num_compte = models.CharField(max_length=11)
#     montant = models.IntegerField()
#
#     interet_debiteur_1 = models.IntegerField()
#     interet_debiteur_2 = models.IntegerField()
#     taxe_interet_debiteur_1 = models.FloatField()
#     taxe_interet_debiteur_2 = models.FloatField()
#
#     taux_commission_mvt = models.FloatField()
#     taux_commission_dec = models.FloatField()
#     commission_mvt = models.IntegerField()
#     commission_dec = models.IntegerField()
#
#     frais_fixe = models.IntegerField()
#     tva = models.IntegerField()
#     taux_tva = models.FloatField()
#
#     net_debit = models.IntegerField()
#     solde_agios = models.IntegerField()
#
#     # type_account = models.CharField(max_length=10, default="Courant")
#
#     date_deb_arrete = models.DateTimeField()
#     date_fin_arrete = models.DateTimeField()
#     date_deb_autorisation = models.DateTimeField()
#     date_fin_autorisation = models.DateTimeField()
#     date_ajout = models.DateTimeField(default=datetime.now)
#
#     class Meta:
#         unique_together = ('num_compte', 'date_deb_arrete', 'date_fin_arrete', 'date_deb_autorisation', 'date_fin_autorisation')


# New classes definitions
#
# class Compte(models.Model):
#     """
#         Account number class definition
#     """
#     num_compte = models.CharField(max_length=11, primary_key=True)
#     intitule_compte = models.CharField(max_length=100)
#     type_account = models.CharField(max_length=10, default='Courant')
#     created_at = models.DateTimeField(auto_now_add=True)
#
#
# class Operation(models.Model):
#     code_operation = models.CharField(max_length=5, unique=True, primary_key=True)
#     libelle_operation = models.CharField(max_length=100, default="Pas de libellé")
#     created_at = models.DateTimeField(auto_now_add=True)


class Echelle(models.Model):
    """
        Defining a class for storing Delta datas
    """
    user = models.ForeignKey(User, related_name="echelles", on_delete=models.CASCADE, null=True)
    code_agence = models.CharField(max_length=20)
    num_compte = models.CharField(max_length=20)
    autorisations = models.JSONField(null=True)
    frais_fixe = models.IntegerField(null=True)
    ircm = models.JSONField(null=True)
    interets_debiteurs = models.JSONField(null=True)
    interets_crediteurs = models.JSONField(null=True)
    tva = models.JSONField(null=True)
    comission_mouvement = models.JSONField(null=True)
    comission_decouvert = models.JSONField(null=True)
    date_deb_arrete = models.DateTimeField()
    date_fin_arrete = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('num_compte', 'date_deb_arrete', 'date_fin_arrete', 'code_agence', 'user')


class Historic(models.Model):
    """
        Defining a class for storing all historics as Json files
    """
    historic = models.JSONField()
    user = models.ForeignKey(User, related_name="historics", on_delete=models.CASCADE, null=True)
    created_at = models.DateTimeField(default=datetime.now)


class Results(models.Model):
    user = models.ForeignKey(User, related_name="results", on_delete=models.CASCADE, null=True)
    result_json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)


class SoldeInitial(models.Model):

    user = models.ForeignKey(User, related_name="soldes", on_delete=models.CASCADE, null=True)
    num_compte = models.CharField(max_length=20)
    intitule = models.CharField(max_length=100)
    solde_initial = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'num_compte')


class ActiveFileUser(models.Model):
    user = models.ForeignKey(User, related_name="active_users", on_delete=models.CASCADE, null=True)
    file = models.ForeignKey(File, related_name="active_users_files", on_delete=models.CASCADE, null=True)
    type = models.CharField(max_length=20)

    class Meta:
        unique_together = ('user', 'file', 'type')


# Statistics
# class Statistics(models.Model):
#     user = models.ForeignKey(User, related_name="active_users", on_delete=models.CASCADE, null=True)
#     num_compte = models.CharField(max_length=20)
#     code_agence = models.CharField(max_length=20)
#     type = models.CharField(max_length=20)
#     calul = models.IntegerField()
#     journal = models.IntegerField()
#     date_deb_arrete = models.DateField()
#     date_fin_arrete = models.DateField()
#
#     class Meta:
#         unique_together = ('num_compte', 'date_deb_arrete', 'date_fin_arrete')
#
#
# class Simulation:
#     user = models.ForeignKey(User, related_name="active_users", on_delete=models.CASCADE, null=True)
#     nombre_compte = models.IntegerField()
#     created_at = models.DateTimeField(auto_now_add=True)