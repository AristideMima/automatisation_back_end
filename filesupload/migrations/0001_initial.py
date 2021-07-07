# Generated by Django 3.2.3 on 2021-07-07 09:16

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Compte',
            fields=[
                ('num_compte', models.CharField(max_length=11, primary_key=True, serialize=False)),
                ('intitule_compte', models.CharField(max_length=100)),
                ('type_account', models.CharField(default='E', max_length=2)),
            ],
        ),
        migrations.CreateModel(
            name='Historique',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('code_agence', models.CharField(max_length=20)),
                ('date_comptable', models.DateTimeField()),
                ('date_valeur', models.DateTimeField()),
                ('num_compte', models.CharField(max_length=11)),
                ('intitule_compte', models.CharField(max_length=100)),
                ('libelle_operation', models.CharField(max_length=100)),
                ('code_operation', models.CharField(max_length=5)),
                ('sens', models.CharField(max_length=2)),
                ('montant', models.IntegerField()),
            ],
        ),
        migrations.CreateModel(
            name='Operation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code_operation', models.CharField(max_length=5, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Delta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code_agence', models.CharField(max_length=20)),
                ('num_compte', models.CharField(max_length=11)),
                ('montant', models.IntegerField()),
                ('interet_debiteur_1', models.IntegerField()),
                ('interet_debiteur_2', models.IntegerField()),
                ('taxe_interet_debiteur_1', models.FloatField()),
                ('taxe_interet_debiteur_2', models.FloatField()),
                ('taux_commission_mvt', models.FloatField()),
                ('taux_commission_dec', models.FloatField()),
                ('commission_mvt', models.IntegerField()),
                ('commission_dec', models.IntegerField()),
                ('frais_fixe', models.IntegerField()),
                ('tva', models.IntegerField()),
                ('taux_tva', models.FloatField()),
                ('net_debit', models.IntegerField()),
                ('solde_agios', models.IntegerField()),
                ('date_deb_arrete', models.DateTimeField()),
                ('date_fin_arrete', models.DateTimeField()),
                ('date_deb_autorisation', models.DateTimeField()),
                ('date_fin_autorisation', models.DateTimeField()),
                ('date_ajout', models.DateTimeField(default=datetime.datetime.now)),
            ],
            options={
                'unique_together': {('num_compte', 'date_deb_arrete', 'date_fin_arrete', 'date_deb_autorisation', 'date_fin_autorisation')},
            },
        ),
        migrations.CreateModel(
            name='Arretes',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code_agence', models.CharField(max_length=20)),
                ('num_compte', models.CharField(max_length=11)),
                ('montant', models.IntegerField()),
                ('date_deb_arrete', models.DateTimeField()),
                ('date_fin_arrete', models.DateTimeField()),
                ('date_deb_autorisation', models.DateTimeField()),
                ('date_fin_autorisation', models.DateTimeField()),
            ],
            options={
                'unique_together': {('num_compte', 'date_deb_arrete', 'date_fin_arrete', 'date_deb_autorisation', 'date_fin_autorisation')},
            },
        ),
    ]
