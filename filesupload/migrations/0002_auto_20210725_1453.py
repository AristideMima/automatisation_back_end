# Generated by Django 3.2.3 on 2021-07-25 14:53

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('filesupload', '0001_initial'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Compte',
        ),
        migrations.DeleteModel(
            name='Operation',
        ),
    ]