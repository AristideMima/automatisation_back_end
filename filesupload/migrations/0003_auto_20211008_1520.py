# Generated by Django 3.2.5 on 2021-10-08 15:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('filesupload', '0002_statisticepargne_statisticourant'),
    ]

    operations = [
        migrations.AddField(
            model_name='statisticepargne',
            name='agence',
            field=models.CharField(default=0, max_length=50),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='statisticourant',
            name='agence',
            field=models.CharField(default=0, max_length=50),
            preserve_default=False,
        ),
    ]
