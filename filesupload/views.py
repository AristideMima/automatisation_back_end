from rest_framework import views
from rest_framework.parsers import BaseParser, MultiPartParser
from rest_framework.response import Response
import pandas as pd
from datetime import timedelta
from .models import *
import re
from rest_framework.decorators import api_view
from math import ceil
from json import load
from rest_framework.permissions import IsAuthenticated
from django.http import JsonResponse
import random
from tqdm import tqdm
import os
from celery import shared_task
from celery_progress.backend import ProgressRecorder
import time

# Constant declarations

# 1- Epargne
TAUX_INT_EPARGNE = 2.45
TAUX_IRCM_EPARGNE = 16.25
TAUX_TVA = 19.25
INITIAL_VALUE = 0
SEUIL_INT_INF = 10000000

# 2- Courant
TAUX_COM_MVT = 0.025
TAUX_DEC = 0.020833
TAUX_INT_DEB = 15.5
LEN_INTERET_DEBITEURS = 3
PATH_HISTORIQUE = "static/historiques/"
PATH_AUTORISATION = "static/autorisations/"
PATH_COMPTE = "static/comptes/"
PATH_SOLDE = "static/soldes/"
PATH_JOURNAUX = "static/journaux/"
PATH_OPERATIONS = "static/operations/"


# Get some statistics
@api_view(['GET'])
def get_staistics(request):

    # Files and user count
    total_files = File.objects.count()
    total_files_solde = File.objects.filter(type="solde").count()
    total_files_journal = File.objects.filter(type="journal").count()
    total_files_historique = File.objects.filter(type="historique").count()
    total_files_autorisation = File.objects.filter(type="autorisation").count()
    total_user = User.objects.count()




@shared_task(bind=True)
def celery_function(self, seconds):
    progress_recorder = ProgressRecorder(self)
    result = 0
    for i in range(seconds):
        time.sleep(1)
        result += i
        progress_recorder.set_progress(i + 1, seconds)
    return result


class FileParser(BaseParser):
    """
        Class based custom parser
    """

    media_type = 'text/plain'

    def parse(self, stream, media_type=None, parser_context=None):
        return stream.read()


global regex_dict

regex_dict = {
    'excel': '[(*.xls)(xlsx]'
}

CODES_PATH = "static/libelle_codes.json"


@api_view(['POST'])
def delete_file(request):
    id = request.data['id']
    type = request.data['type']

    # Delete file inside disk and delete inside database
    file = File.objects.get(id=id)
    file_path = file.file_path

    dict_paths = {"autorisation": PATH_AUTORISATION, "solde": PATH_SOLDE, "historique": PATH_HISTORIQUE,
                  "operation": PATH_OPERATIONS, "compte": PATH_COMPTE, "journal": PATH_JOURNAUX}

    complete_path = dict_paths[type] + file_path

    if os.path.exists(complete_path):

        try:
            os.remove(complete_path)

            # Remove also accounts and operations if historique type
            if type == "historique":
                compte_path = PATH_COMPTE + file_path
                operation_path = PATH_OPERATIONS + file_path
                os.remove(compte_path)
                os.remove(operation_path)

            file.delete()
            ActiveFileUser.objects.filter(file_id=id).delete()
        except Exception as e:
            print(e)
            default_response = JsonResponse({"message": "Erreur lors de la suppression"}, status=500)
            return default_response
    else:
        default_response = JsonResponse({"message": "Ce fichier n'existe pas"}, status=500)
        return Response(default_response)

    return Response(204)


@api_view(['POST'])
def set_active_file(request):
    type = request.data['type_file']
    user = request.user
    id = request.data['id']

    file = File.objects.get(id=id)

    # Check if present inside dataBase
    file_active = None
    try:
        file_active = ActiveFileUser.objects.get(user=user, type=type)
    except:
        pass
    if file_active is not None:
        file_active.file = file
        file_active.save()
    else:
        # Create or update file
        try:
            ActiveFileUser.objects.create(user=user, type=type, file=file)
        except Exception as e:
            default_response = JsonResponse({"message": "Erreur lors de la mise à jour"}, status=500)
            return default_response

    # return new added files

    return Response(200)


@api_view(['POST'])
def get_files_list(request):
    type = request.data['type_file']
    user = request.user

    file = retrieve_files(type, user)

    return Response(file)


# Get last files
def retrieve_files(type, user):
    res = []
    try:
        files = pd.DataFrame(list(File.objects.filter(file_type=type).all().values()))
        files['index'] = files.index + 1
        files['created_at'] = files['created_at'].dt.date

        active_files = pd.DataFrame(list(ActiveFileUser.objects.filter(type=type, user=user).all().values()))
        if len(active_files) != 0:
            active_id = active_files['file_id'].iloc[0]
            files['active_file'] = files['id'].apply(lambda x: True if x == active_id else False)
        res = files.T.to_dict().values()
    except Exception as e:
        pass

    return res


@api_view(['POST'])
def make_calcul(request):
    # Get data passed by request
    # We will compute all data separately

    # Read Type, Read mode
    # Load latest history for computation

    default_response = JsonResponse({"message": "Informations incorrectes"}, status=500)

    # Load parameters
    try:
        accounts = pd.DataFrame(request.data['accounts'])
        options = request.data['options']
        operations = pd.DataFrame(request.data['operations'])
        type_account = request.data['type_account']
        user = request.user

        if type_account == "Courant":
            accounts['debut_autorisation'] = pd.to_datetime(accounts['debut_autorisation'])
            accounts['fin_autorisation'] = pd.to_datetime(accounts['fin_autorisation'])
        commision_mouvement = request.data['com_mvt']
        commission_decouvert = request.data['com_dec']
        date_deb = pd.to_datetime(options["date_deb"])
        date_fin = pd.to_datetime(options["date_fin"])
        type_arrete = request.data['type_arrete']
        ordre = request.data['ordre']
        int_epargne = request.data['int_epargne']
    except Exception as e:
        print(e)
        return default_response

    # Load latest history
    try:

        try:
            req = ActiveFileUser.objects.get(user=user, type="historique")
            last_history = File.objects.get(id=req.file)
        except:
            last_history = File.objects.get(active_file=True, file_type="historique")
        path_history = PATH_HISTORIQUE + last_history.file_path
        history = pd.DataFrame(pd.read_csv(path_history, compression="gzip"))
        history['N° Compte'] = history['N° Compte'].astype(str).str.zfill(11)
        history['Date Comptable'] = pd.to_datetime(history['Date Comptable'])
        history['Date de Valeur'] = pd.to_datetime(history['Date de Valeur'])


    except FileNotFoundError as e:
        return default_response

    # Load Journal
    try:

        try:
            req = ActiveFileUser.objects.get(user=user, type="journal")
            last_journal = File.objects.get(id=req.file)
        except:
            last_journal = File.objects.get(active_file=True, file_type="journal")
        path_journal = PATH_JOURNAUX + last_journal.file_path
        journal = pd.DataFrame(pd.read_csv(path_journal, compression="gzip"))
        journal['Numero de compte'] = journal['Numero de compte'].astype(str).str.zfill(11)

    except FileNotFoundError as e:
        print(e)

    # If we are not doing regularisation
    if not type_arrete:
        accounts = accounts[['num_compte']]
        accounts.rename(columns={'num_compte': 'N° Compte'}, inplace=True)

        data_sold, data_auto = [None] * 2
        try:
            try:
                req = ActiveFileUser.objects.get(user=user, type="solde")
                last_solde = File.objects.get(id=req.file)
            except:
                last_solde = File.objects.get(active_file=True, file_type="solde")
            path_solde = PATH_SOLDE + last_solde.file_path
            data_sold = pd.DataFrame(pd.read_csv(path_solde))
            data_sold['N° Compte'] = data_sold['N° Compte'].astype(str).str.zfill(11)
            data_sold['Date Solde'] = pd.to_datetime(data_sold['Date Solde'])

            data_sold = data_sold[(date_deb > data_sold['Date Solde'])]
            data_sold.sort_values(by="Date Solde", ascending=False, inplace=True)
        except Exception as e:
            print(e)
        pass

        if data_sold is not None:

            accounts = accounts.merge(data_sold[['N° Compte', 'Solde']], on='N° Compte', how="left")
            accounts = accounts.groupby(['N° Compte']).first().reset_index()
            accounts.rename(columns={"Solde": "solde_initial"}, inplace=True)
            accounts['solde_initial'].fillna(0, inplace=True)

        else:
            accounts['solde_initial'] = 0

        if type_account == "Courant":
            # Add last sold
            # Add autorisations
            try:
                try:
                    req = ActiveFileUser.objects.get(user=user, type="autorisation")
                    last_auto = File.objects.get(id=req.file)
                except:
                    last_auto = File.objects.get(active_file=True, file_type="autorisation")
                path_auto = PATH_AUTORISATION + last_auto.file_path
                data_auto = pd.read_csv(path_auto, compression="gzip")
                data_auto['N° Compte'] = data_auto['N° Compte'].astype(str).str.zfill(11)
                data_auto = data_sold[
                    ((date_deb >= data_sold['Date Mise en Place']) & (data_sold['Date de fin'] >= date_fin))]
                data_auto.sort_values(by="Montant", ascending=False, inplace=True)
            except:
                pass

            if data_auto is not None:
                accounts = accounts.merge(data_auto[['Date de fin', 'Date Mise en Place', 'Montant', 'N° Compte']],
                                          on='N° Compte', how="left")
                accounts = accounts.groupby(['N° Compte']).first().reset_index()
                accounts.rename(columns={'Date de fin': 'fin_autorisation', 'Montant': 'montant',
                                         'Date Mise en Place': 'debut_autorisation'}, inplace=True)
                accounts['montant'].fillna(0, inplace=True)
                accounts['fin_autorisation'].fillna("", inplace=True)
                accounts['debut_autorisation'].fillna("", inplace=True)
            else:
                accounts['montant'] = 0
                accounts['debut_autorisation'] = ""
                accounts['fin_autorisation'] = ""

            accounts.rename(columns={"N° Compte": "num_compte"}, inplace=True)
            accounts['debut_autorisation'] = pd.to_datetime(accounts['debut_autorisation'])
            accounts['fin_autorisation'] = pd.to_datetime(accounts['fin_autorisation'])

    try:
        accounts.rename(columns={"N° Compte": "num_compte"}, inplace=True)
    except Exception as e:
        pass

    # Filter by account & by operations
    unique_accounts = list(accounts['num_compte'].unique())
    unique_operation = list(operations['code_operation'].unique())
    history = history[(history['N° Compte'].isin(unique_accounts) & history['Code Opération'].isin(unique_operation))]
    # compute real sold based on
    restriced_history = history[(date_deb < history['Date de Valeur'])][['N° Compte', 'Montant', 'Sens']]

    history = history[((date_deb <= history['Date de Valeur']) & (history['Date de Valeur'] <= date_fin))]

    # Check result len
    if len(history) == 0:
        return JsonResponse({"message": "Aucun historique sur cette date pour les comptes choisis"}, status=500)

    if ordre:
        history = range_file(history)

    # Compute stuff

    results = []
    compressed_results = []
    if type_account == "Courant":
        for index, account in tqdm(accounts[:500].iterrows(), total=accounts[:500].shape[0]):


            filter_data = history[history['N° Compte'] == account["num_compte"]]
            if len(filter_data) == 0:
                continue

            # Update initial solde
            # filter_rest = restriced_history[restriced_history['N° Compte'] == account["num_compte"]]
            # try:
            #     credit = filter_rest[filter_rest.Sens == "C"]['Montant'].sum()
            #     debit = filter_rest[filter_rest.Sens == "D"]['Montant'].sum()
            #
            #     account['solde_initial'] = account['solde_initial'] + credit - debit
            # except Exception as e:
            #     return default_response
            #     print(e)

            first = computation_first_table(filter_data, account, operations, date_deb)

            second = computation_second_table(pd.DataFrame(first), options, commision_mouvement, commission_decouvert)

            # Add detailled Results
            new_first = [dict(zip(first, t)) for t in zip(*first.values())]

            new_second = []

            new_first.append({k: "" for k in list(first.keys())})
            res_1 = {'LIBELLES': "TOTAL", 'DEBIT_MVTS': sum(first['DEBIT_MVTS']),
                     "CREDIT_MVTS": sum(first['CREDIT_MVTS']),
                     "jrs": sum(first['jrs']), 'SOLDES_NBR': sum(first['SOLDES_NBR']), 'MVTS_13': sum(first['MVTS_13']),
                     'MVTS_14': sum(first['MVTS_14'])}
            new_first.append(res_1)

            new_first.append({k: "" for k in list(first.keys())})
            new_first.append({k: "" for k in list(first.keys())})
            new_first.append(
                {"SOLDES": "DESIGNATION", "SOLDE_JOUR": "TAUX", "jrs": "AGIOS", "DEBITS_NBR": "AMPLITUDE",
                 "CREDIT_NBR": "ECART"})
            for i, key in enumerate(list(second.keys())):
                part_dict = {"col_0": key, "id": i}
                part_dict.update({"col_" + str(i + 1): col for i, col in enumerate(second[key])})
                new_second.append(part_dict)
                res = {'SOLDES': key, "SOLDE_JOUR": second[key][0], "jrs": second[key][1]}
                new_first.append(res)

            data_first = {'first': new_first, 'account': account["num_compte"], "second": new_second}
            # results.append({'first': new_first, 'account': account["num_compte"], "second": new_second})

            # Add compressed Results
            try:
                account_journal_value = \
                journal[journal["Numero de compte"] == account["num_compte"]]['Net client'].iloc[0]
                ecart = (second['TOTAL'][-1]) - account_journal_value
                data_compressed = {"id": index, "N° Compte": account["num_compte"], "Calcul": second['TOTAL'][-1],
                                   "Journal": account_journal_value, "Ecart": ecart, "date_deb": options["date_deb"],
                                   "date_fin": options["date_fin"]}
                # compressed_results.append({"id": id, "N° Compte": account["num_compte"], "Calcul": second['TOTAL'][-1], "Journal":account_journal_value, "Ecart": ecart, "date_deb": options["date_deb"], "date_fin": options["date_fin"]})
            except:
                data_compressed = {"id": index, "N° Compte": account["num_compte"], "Calcul": second['TOTAL'][-1],
                                   "Journal": "Valeur absente", "Ecart": "", "date_deb": options["date_deb"],
                                   "date_fin": options["date_fin"]}
                pass

            results.append(data_first)
            compressed_results.append(data_compressed)
    elif type_account == "Epargne":
        for index, account in tqdm(accounts[:500].iterrows(), total=accounts[:500].shape[0]):

            filter_data = history[history['N° Compte'] == account["num_compte"]]
            if len(filter_data) == 0:
                continue
            filter_rest = restriced_history[restriced_history['N° Compte'] == account["num_compte"]]
            try:
                credit = filter_rest[filter_rest.Sens == "C"]['Montant'].sum()
                debit = filter_rest[filter_rest.Sens == "D"]['Montant'].sum()

                account['solde_initial'] = account['solde_initial'] + credit - debit
            except Exception as e:
                print(e)
            first = computation_first_table_epargne(filter_data, account, operations, int_epargne, date_deb)

            second = computation_second_table_epargne(pd.DataFrame(first), options, int_epargne)

            # Add detail Results
            new_first = [dict(zip(first, t)) for t in zip(*first.values())]

            new_second = []

            new_first.append({k: "" for k in list(first.keys())})
            res_1 = {'LIBELLES': "TOTAL", 'DEBIT_MVTS': sum(first['DEBIT_MVTS']),
                     "CREDIT_MVTS": sum(first['CREDIT_MVTS']),
                     "jrs": sum(first['jrs']), 'SOLDES_NBR': sum(first['SOLDES_NBR']), 'MVTS_13': sum(first['MVTS_13']),
                     'MVTS_14': sum(first['MVTS_14'])}
            new_first.append(res_1)

            new_first.append({k: "" for k in list(first.keys())})
            new_first.append({k: "" for k in list(first.keys())})
            new_first.append(
                {"SOLDES": "DESIGNATION", "SOLDE_JOUR": "TAUX", "jrs": "AGIOS", "DEBITS_NBR": "AMPLITUDE",
                 "CREDIT_NBR": "ECART"})
            for i, key in enumerate(list(second.keys())):
                part_dict = {"col_0": key, "key": i}
                part_dict.update({"col_" + str(i + 1): col for i, col in enumerate(second[key])})
                new_second.append(part_dict)
                res = {'SOLDES': key, "SOLDE_JOUR": second[key][0], "jrs": second[key][1]}
                new_first.append(res)

            data_first = {'first': new_first, 'account': account["num_compte"], "second": new_second}

            # Add compressed Results
            try:
                account_journal_value = \
                journal[journal["Numero de compte"] == account["num_compte"]]['Net client'].iloc[0]
                ecart = (second['TOTAL'][-1]) - account_journal_value
                data_compressed = {"id": index, "N° Compte": account["num_compte"], "Calcul": second['TOTAL'][-1],
                                   "Journal": account_journal_value, "Ecart": ecart, "date_deb": options["date_deb"],
                                   "date_fin": options["date_fin"]}

            except:
                data_compressed = {"id": index, "N° Compte": account["num_compte"], "Calcul": second['TOTAL'][-1],
                                   "Journal": "Valeur absente", "Ecart": "", "date_deb": options["date_deb"],
                                   "date_fin": options["date_fin"]}
                pass

            results.append(data_first)
            compressed_results.append(data_compressed)
    return Response({"all_data": results, "compressed_data": compressed_results})


@api_view(['POST'])
def get_infos(request):
    # Check con

    user = request.user
    data = request.data
    # Define direction and account type
    type_account = data['type_account']

    default_data = Response({"accounts": [], "operations": []})

    # Read last historic
    try:
        try:
            req = ActiveFileUser.objects.get(user=user, type="historique")
            last_history = File.objects.get(id=req.file)
        except:
            last_history = File.objects.get(active_file=True, file_type="historique")
    except FileNotFoundError as e:
        return default_data

    try:
        # Basics data reading
        path_account = PATH_COMPTE + last_history.file_path
        path_operation = PATH_OPERATIONS + last_history.file_path
        accounts = pd.DataFrame(pd.read_csv(path_account, compression="gzip"))
        accounts = accounts[accounts['Type de Compte'] == type_account].copy()
        accounts['N° Compte'] = accounts['N° Compte'].astype(str).str.zfill(11)
        operations = pd.DataFrame(pd.read_csv(path_operation, compression="gzip"))
        operations['key'] = operations.index

    except Exception as e:
        print(e)
        return default_data

    # Read last solde
    data_sold, data_auto = [None] * 2
    try:
        try:
            req = ActiveFileUser.objects.get(user=user, type="solde")
            last_solde = File.objects.get(id=req.file)
        except:
            last_solde = File.objects.get(active_file=True, file_type="solde")
        path_solde = PATH_SOLDE + last_solde.file_path
        data_sold = pd.read_csv(path_solde)
        data_sold['N° Compte'] = data_sold['N° Compte'].astype(str).str.zfill(11)
    except:
        pass

    # Add last sold
    if data_sold is not None:

        accounts = accounts.merge(data_sold[['N° Compte', 'Solde']], on='N° Compte', how="left")
        # accounts = accounts.groupby(['N° Compte']).first().reset_index()
        accounts.rename(columns={"Solde": "solde_initial"}, inplace=True)
        accounts['solde_initial'].fillna(0, inplace=True)


    else:
        accounts['solde_initial'] = 0

    if type_account == "Courant":
        # Add autorisations
        try:
            try:
                req = ActiveFileUser.objects.get(user=user, type="autorisation")
                last_auto = File.objects.get(id=req.file)
            except:
                last_auto = File.objects.get(active_file=True, file_type="autorisation")

            path_auto = PATH_AUTORISATION + last_auto.file_path
            data_auto = pd.read_csv(path_auto, compression="gzip")
            data_auto['N° Compte'] = data_auto['N° Compte'].astype(str).str.zfill(11)
        except:
            pass

        if data_auto is not None:
            accounts = accounts.merge(data_auto[['Date de fin', 'Date Mise en Place', 'Montant', 'N° Compte']],
                                      on='N° Compte', how="left")
            # accounts = accounts.groupby(['N° Compte']).first().reset_index()
            accounts.rename(columns={'Date de fin': 'fin_autorisation', 'Montant': 'montant',
                                     'Date Mise en Place': 'debut_autorisation'}, inplace=True)
            accounts['montant'].fillna(0, inplace=True)
            accounts['fin_autorisation'].fillna("", inplace=True)
            accounts['debut_autorisation'].fillna("", inplace=True)
        else:
            accounts['montant'] = 0
            accounts['debut_autorisation'] = ""
            accounts['fin_autorisation'] = ""

    # Finish
    # res_accounts = accounts[accounts['Type de Compte'] == type_account].copy()
    res_accounts = accounts.copy()
    res_accounts.rename(columns={"N° Compte": "num_compte", "Type de Compte": "type_compte"}, inplace=True)
    res_accounts['key'] = res_accounts.index

    res_accounts = list(res_accounts.T.to_dict().values())

    return Response({"accounts": res_accounts, "operations": operations.T.to_dict().values()})


class FileUpload(views.APIView):
    """
        Class based file upload
    """
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated]

    # file upload function
    def put(self, request, format=None):

        files = request.FILES.getlist('files[]')

        if len(files) == 0:
            return Response(500)

        file = files[0]
        file_path = str(file) + "---" + str(datetime.now()).replace(":", "-") + ".csv"

        choice = request.data['choice']

        if request.user.type != "dcpo":
            default_response = JsonResponse({"message": " Vous n'êtes pas autorisé à faire cette opération"},
                                            status=500)
            return Response(default_response)

        # Match corresponding choices
        if choice == "historique":

            try:
                datas = pd.read_csv(file, header=None, low_memory=False, sep="|")
                datas.rename(columns={0: "Date Comptable", 1: "Code Agence", 2: "N° Compte", 3: "Devise", 5: "Sens",
                                      6: "Montant", 7: "Code Opération", 8: "Libellé Opération", 10: "Date de Valeur"},
                             inplace=True)
                cols = ["Date Comptable", "Code Agence", "N° Compte", "Sens", "Montant", "Code Opération",
                        "Libellé Opération", "Date de Valeur"]

                # Will be drop later 
                datas.dropna(subset=cols, inplace=True)

                final_data = datas[cols]

                final_data = datas[cols].copy()

                # Fill values
                final_data['Date Comptable'] = pd.to_datetime(final_data['Date Comptable'], errors="ignore").dt.date
                final_data['Date de Valeur'] = pd.to_datetime(final_data['Date de Valeur'], errors="ignore").dt.date

                final_data["Code Opération"] = final_data["Code Opération"].astype(int)

                # Str columns
                for col in ["Sens", "Libellé Opération", "Code Opération", "Code Agence",
                            "Montant"]:
                    final_data[col] = final_data[col].astype(str)

                final_data['N° Compte'] = final_data['N° Compte'].apply(lambda x: str(x).zfill(11))
                final_data['Code Agence'] = final_data['Code Agence'].apply(lambda x: str(x).zfill(5))
                final_data['N° Compte'] = final_data['Code Agence'] + "-" + final_data['N° Compte']

                # Processing Amount
                final_data['Montant'] = final_data['Montant'].apply(lambda x: int(x.split(",")[0]))
                comptes = pd.DataFrame({"N° Compte": final_data['N° Compte'].unique()})
                comptes['Type de Compte'] = final_data['N° Compte'].apply(
                    lambda x: "Epargne" if x[-4:-1] == "110" else "Courant")

                path_histo = PATH_HISTORIQUE + file_path
                path_operations = PATH_OPERATIONS + file_path
                path_compte = PATH_COMPTE + file_path

                # Processing operations
                operations = pd.DataFrame({"Code Opération": final_data['Code Opération'].unique()})

                global codes
                with open(CODES_PATH, "r") as file_codes:
                    codes = load(file_codes)

                operations['libelle_operation'] = operations['Code Opération'].apply(fill_operation)
                operations.rename(columns={"Code Opération": "code_operation"}, inplace=True)

                # save datas 
                # Update latest record
                try:
                    modify_last_record(choice)
                except File.DoesNotExist:
                    pass

                options = {"date_inf": final_data['Date Comptable'].min(),
                           "date_sup": final_data['Date Comptable'].max(), "len": len(final_data)}

                res = save_file(request.user, file_path, choice, options)
                if res is not None:
                    return JsonResponse({"message": "Le fichier {} est déjà présent en base de données".format(file)},status=500)

                final_data.to_csv(path_histo, index=False, compression="gzip")
                comptes.to_csv(path_compte, index=False, compression="gzip")
                operations.to_csv(path_operations, index=False, compression="gzip")

            except Exception as e:
                print(e)
                return JsonResponse(
                    {"message": "Le fichier {} ne respecte pas le format exigé - voir le guide".format(file)},
                    status=500)

        elif choice == "solde":

            # Loading all initial soldes inside the data base
            try:

                datas_soldes = pd.read_csv(file, header=None, sep='|')
                datas_soldes.rename(
                    columns={0: "Code Agence", 1: "Devise", 2: "N° Compte", 3: "Année", 4: "Mois", 6: "Date Solde",
                             7: "Solde", 8: "Date Mois Suivant"}, inplace=True)

                datas_soldes['N° Compte'] = datas_soldes['N° Compte'].apply(lambda x: str(x).zfill(11))
                datas_soldes['Code Agence'] = datas_soldes['Code Agence'].apply(lambda x: str(x).zfill(5))
                datas_soldes['Date Solde'] = pd.to_datetime(datas_soldes['Date Solde'], errors="ignore").dt.date
                datas_soldes['N° Compte'] = datas_soldes['Code Agence'] + "-" + datas_soldes['N° Compte']
                # datas_soldes['Date Mois Suivant'] = pd.to_datetime(datas_soldes['Date Mois Suivant'],
                #                                                    errors="ignore").dt.date
                # datas_soldes.sort_values(by='Date Solde', ascending=False, inplace=True)
                # datas_soldes.drop_duplicates(subset='N° Compte', keep='first', inplace=True)
                datas_soldes['Solde'] = datas_soldes['Solde'].apply(lambda x: int(x.split(",")[0]))
                datas_soldes = datas_soldes[['N° Compte', 'Solde', 'Date Solde']]
                # datas_soldes['Mois'] = datas_soldes['Mois'].apply(lambda x: int(x.split(",")[0]))

            except Exception as e:
                print(e)
                return JsonResponse(
                    {"message": "Le fichier {} ne respecte pas le format exigé - voir le guide".format(file)},
                    status=500)

            if datas_soldes.isnull().sum().sum() != 0:
                return JsonResponse({"message": "Le fichier {} contient des valeurs nulles".format(file)}, status=500)

            # save soldes datas on disk and save it in database
            try:
                # Update latest record
                try:
                    modify_last_record(choice)
                except File.DoesNotExist:
                    pass

                # Save new added file
                options = {"date_inf": datas_soldes['Date Solde'].min(),
                           "date_sup": datas_soldes['Date Solde'].max(), "len": len(datas_soldes)}
                res = save_file(request.user, file_path, choice, options)

                if res is not None:
                    return JsonResponse(
                        {"message": "Le fichier {} est déjà présent en base de données".format(file)},
                        status=500)

                path_solde = PATH_SOLDE + file_path
                datas_soldes.to_csv(path_solde, index=False)

            except Exception as e:
                return JsonResponse(
                    {"message": "Une erreur est survenue lors de l'enregistrement du fichier {}".format(file)},
                    status=500)

        elif choice == "autorisation":

            try:
                datas_autorisations = pd.read_csv(file, sep="|", header=None)
                datas_autorisations.rename(
                    columns={0: "Code Agence", 1: "N° Compte", 2: "Clé", 3: "Date Mise en Place", 4: "Date de fin",
                             5: "Montant", 6: "Taux"}, inplace=True)

                if datas_autorisations[
                    ["N° Compte", "Date Mise en Place", "Date de fin", "Montant"]].isnull().sum().sum() != 0:
                    return JsonResponse({"message": "Le fichier {} contient des valeurs nulles".format(file)},
                                        status=500)

                datas_autorisations['Date Mise en Place'] = pd.to_datetime(datas_autorisations['Date Mise en Place']).dt.date
                datas_autorisations['Date de fin'] = pd.to_datetime(datas_autorisations['Date de fin']).dt.date
                datas_autorisations['Montant'] = datas_autorisations['Montant'].apply(lambda x: int(x.split(",")[0]))
                # datas_autorisations.sort_values(by='Date Mise en Place', ascending=False, inplace=True)
                # datas_autorisations.drop_duplicates(subset='N° Compte', keep='first', inplace=True)
                datas_autorisations['N° Compte'] = datas_autorisations['N° Compte'].apply(lambda x: str(x).zfill(11))
                datas_autorisations['Code Agence'] = datas_autorisations['Code Agence'].apply(lambda x: str(x).zfill(5))
                datas_autorisations['N° Compte'] = datas_autorisations['Code Agence'] + "-" + datas_autorisations['N° Compte']
                path_auto = PATH_AUTORISATION + file_path

                try:
                    modify_last_record(choice)
                except File.DoesNotExist:
                    pass

                # Save new added file
                options = {"date_inf": datas_autorisations['Date Mise en Place'].min(),
                           "date_sup": datas_autorisations['Date de fin'].max(), "len": len(datas_autorisations)}
                res = save_file(request.user, file_path, choice, options)
                if res is not None:
                    return JsonResponse(
                        {"message": "Le fichier {} est déjà présent en base de données".format(file)},
                        status=500)

                datas_autorisations[["N° Compte", "Date Mise en Place", "Date de fin", "Montant"]].to_csv(path_auto,
                                                                                                          index=False,
                                                                                                          compression="gzip")
            except:
                return JsonResponse(
                    {"message": "Une erreur est survenue lors de l'enregistrement du fichier {}".format(file)},
                    status=500)

        elif choice == "journal":
            try:
                data_journal = pd.read_csv(file, sep=";")
                data_journal.rename(
                    columns={0: "Numero de compte", 1: "Net client"}, inplace=True)
                data_journal.drop_duplicates(subset="Numero de compte", inplace=True)
                new_data_journal = data_journal[['Numero de compte', 'Net client']]
                new_data_journal.dropna(inplace=True)
                new_data_journal["Numero de compte"] = new_data_journal["Numero de compte"].astype(str)
                new_data_journal["Numero de compte"] = new_data_journal["Numero de compte"].apply(clean_account)
                new_data_journal["Net client"] = new_data_journal["Net client"].apply(clean_net_client)

                try:
                    modify_last_record(choice)
                except File.DoesNotExist as e:
                    print(e)

                path_journal = PATH_JOURNAUX + file_path

                # Save new added file
                date_deb = datetime.strptime(
                    '{}-{}-{}'.format(random.randint(2000, 2050), random.randint(1, 12), random.randint(1, 30)),
                    '%Y-%m-%d')
                date_fin = datetime.strptime(
                    '{}-{}-{}'.format(random.randint(2050, 2100), random.randint(1, 12), random.randint(1, 30)),
                    '%Y-%m-%d')
                options = {"date_inf": date_deb, "date_sup": date_fin, "len": len(data_journal)}

                res = save_file(request.user, file_path, choice, options)
                if res is not None:
                    return JsonResponse(
                        {"message": "Le fichier {} est déjà présent en base de données".format(file)},
                        status=500)

                new_data_journal.to_csv(path_journal, compression="gzip")
            except Exception as e:
                print(e)
                return JsonResponse(
                    {"message": "Une erreur est survenue lors de l'enregistrement du fichier {}".format(file)},
                    status=500)

        return Response(204)


def clean_net_client(net_client):
    res = re.sub(r'[a-zA-Z\.,]', '', str(net_client))
    res = res.replace(".", "")
    return int(res)


def clean_account(account):
    res = account.split()[0]

    res = str(res).zfill(11)

    return res


def fill_operation(code_operation):
    libelle_operation = "No libelle"
    try:
        libelle_operation = codes[code_operation]
    except Exception as e:
        pass

    return libelle_operation


# Modify last record 
def modify_last_record(choice):
    prev = File.objects.get(active_file=True, file_type=choice)
    prev.active_file = False
    prev.save()


def save_file(user, file_path, choice, options):
    try:
        new_file = File()
        new_file.user = user
        new_file.file_path = file_path
        new_file.file_type = choice
        new_file.date_inf = options['date_inf']
        new_file.date_sup = options['date_sup']
        new_file.longueur = options['len']
        new_file.active_file = True
        new_file.save()
        return None
    except Exception as e:
        print(e)
        return "oups"


# Processing functions
def range_file(data_excel):
    res_filter_date = data_excel.copy()

    res_filter_date['index'] = res_filter_date.index
    res_filter_date = res_filter_date.sort_values(by=['Date de Valeur', 'index'])
    res_filter_date = res_filter_date.drop(columns='index')

    return res_filter_date


# ----- System conform computation -----#

# Computation function for courant
def computation_first_table(datas, account, operations, date_deb):
    # Initialization
    cols = ['CPTABLE', 'VALEUR', 'LIBELLES', 'DEBIT_MVTS', 'CREDIT_MVTS', 'SOLDES', 'SOLDE_JOUR', 'jrs', 'DEBITS_NBR',
            'CREDIT_NBR', 'SOLDES_NBR', 'MVTS_13', 'MVTS_14']
    res_data = {col: [] for col in cols}

    # Initialization

    # Computation part

    # First part
    res_filter_date = datas.copy()

    montant_account = int(account['montant'])

    # range by date value
    res_filter_date['index'] = res_filter_date.index
    res_filter_date = res_filter_date.sort_values(by=['Date de Valeur', 'index'])
    res_filter_date = res_filter_date.drop(columns='index')
    temp_datas = res_filter_date.copy()
    date_valeur = temp_datas['Date de Valeur'].tolist()

    sold = int(account['solde_initial'])
    j = 1

    date_initiale = date_deb.replace(day=1) - timedelta(days=1)
    res_data['VALEUR'].append(date_initiale.strftime('%d/%m/%Y'))
    res_data['CPTABLE'].append("")
    res_data['LIBELLES'].append("SOLDE INITIAL")

    if sold <= 0:
        res_data['DEBIT_MVTS'].append(-1 * sold)
        res_data['CREDIT_MVTS'].append(0)
    else:
        res_data['DEBIT_MVTS'].append(0)
        res_data['CREDIT_MVTS'].append(sold)

    res_data['SOLDES'].append(-res_data['DEBIT_MVTS'][-1] + res_data['CREDIT_MVTS'][-1])
    soldes = res_data['SOLDES'][-1]
    jrs = abs((date_initiale - date_valeur[0]).days)
    res_data['SOLDE_JOUR'].append(soldes if jrs != 0 else 0)
    res_data['jrs'].append(jrs)
    debit_nombre = -soldes * jrs if soldes < 0 else 0
    credit_nombre = soldes * jrs if soldes > 0 else 0
    res_data['DEBITS_NBR'].append(debit_nombre)
    res_data['CREDIT_NBR'].append(credit_nombre)
    soldes_nombre = -soldes if soldes < 0 else 0
    res_data['SOLDES_NBR'].append(soldes_nombre)
    soldes_nbr = res_data['SOLDES_NBR'][-1]

    if montant_account != 0:
        deb_autorisation = account['debut_autorisation']
        fin_autorisation = account['fin_autorisation']
        if deb_autorisation <= date_deb <= fin_autorisation:
            mvt_13 = soldes_nbr * jrs if soldes_nbr <= account['montant'] else account['montant'] * jrs
            res_data['MVTS_13'].append(mvt_13)
        else:
            res_data['MVTS_13'].append(0)
    else:
        res_data['MVTS_13'].append(0)

    mvt_14 = debit_nombre - res_data['MVTS_13'][-1]
    res_data['MVTS_14'].append(mvt_14)

    j = 1
    l = len(date_valeur)
    # Loop and compute values
    for i in range(len(date_valeur)):

        # 1 et 2
        date_cpt = temp_datas.iloc[i]['Date Comptable']
        date_val = date_valeur[i]
        code_operation = temp_datas.iloc[i]['Code Opération']
        row_code_operation = operations[operations.code_operation == code_operation].iloc[0]

        res_data['CPTABLE'].append(date_cpt.strftime('%d/%m/%Y'))
        res_data['VALEUR'].append(date_val.strftime('%d/%m/%Y'))

        # 3
        res_data['LIBELLES'].append(temp_datas.iloc[i]['Libellé Opération'])

        # 4 & 5
        debit_mvt = 0
        credit_mvt = 0
        montant = temp_datas.iloc[i]['Montant']

        if temp_datas.iloc[i].Sens == "D":
            debit_mvt = montant
        else:
            credit_mvt = montant

        res_data['DEBIT_MVTS'].append(debit_mvt)
        res_data['CREDIT_MVTS'].append(credit_mvt)

        soldes += res_data['CREDIT_MVTS'][-1] - res_data['DEBIT_MVTS'][-1]
        res_data['SOLDES'].append(soldes)

        if j < l - 1:
            jrs = abs((date_valeur[j] - date_val).days)
        else:
            jrs = 0
        j = j + 1

        res_data['SOLDE_JOUR'].append(soldes if jrs != 0 else 0)
        res_data['jrs'].append(jrs)
        debit_nombre = -soldes * jrs if soldes < 0 else 0
        credit_nombre = soldes * jrs if soldes > 0 else 0
        res_data['DEBITS_NBR'].append(debit_nombre)
        res_data['CREDIT_NBR'].append(credit_nombre)
        soldes_nombre = soldes if (soldes < 0 and jrs > 0) else 0

        res_data['SOLDES_NBR'].append(soldes_nombre)
        soldes_nbr = res_data['SOLDES_NBR'][-1]

        # Check if account has a discover
        if montant_account != 0:
            deb_autorisation = account['debut_autorisation']
            fin_autorisation = account['fin_autorisation']
            if deb_autorisation <= date_val <= fin_autorisation:
                mvt_13 = soldes_nbr * jrs if soldes_nbr <= account['montant'] else account['montant'] * jrs

                res_data['MVTS_13'].append(mvt_13)
                # res_data['MVTS_14'].append(mvt_14)
            else:
                res_data['MVTS_13'].append(0)
        else:
            res_data['MVTS_13'].append(0)
        mvt_14 = debit_nombre - res_data['MVTS_13'][-1]
        res_data['MVTS_14'].append(mvt_14)
    return res_data


def computation_second_table(res_data, options, commision_mouvement, commission_decouvert):
    # Get taux_interets_debiteurs
    taux_int_1 = options['taux_interet_debiteur_1'] / 100
    taux_int_2 = options["taux_interet_debiteur_2"] / 100
    taux_int_3 = options["taux_interet_debiteur_3"] / 100
    taux_com_mvts = options["taux_commision_mouvement"] / 100
    taux_com_dec = options["taux_commision_decouvert"] / 100
    tva = options["taux_tva"] / 100
    frais_fixe = 0

    cols_calcul = ['INT_DEBITEURS_1', 'INT_DEBITEURS_2', 'INT_DEBITEURS_3', 'COM_DE_MVTS', 'COM_DE_DVERT',
                   'FRAIS_FIXES', 'TVA', 'TOTAL']
    calcul = {col: [] for col in cols_calcul}

    # # 14
    res = (sum(res_data['MVTS_13']) * taux_int_1) / 360
    calcul['INT_DEBITEURS_1'].append(ceil(res))

    # 15
    res = (sum(res_data['MVTS_14']) * taux_int_2) / 360
    calcul['INT_DEBITEURS_2'].append(ceil(res))

    res = (sum(res_data['MVTS_14']) * taux_int_3) / 360
    calcul['INT_DEBITEURS_3'].append(ceil(res))

    # 16

    if not commision_mouvement:
        seuil = 2000

        int_sum = sum(res_data['DEBIT_MVTS'][1:]) * taux_com_mvts

        res = seuil if int_sum < seuil else int_sum
        calcul['COM_DE_MVTS'].append(ceil(res))
    else:
        calcul['COM_DE_MVTS'].append(0)

    # 17
    if not commission_decouvert:
        total_plus_fort = min(res_data['SOLDE_JOUR'])
        res = 0 if total_plus_fort >= 0 else -total_plus_fort * taux_com_dec
        calcul['COM_DE_DVERT'].append(ceil(res))
    else:
        calcul['COM_DE_DVERT'].append(0)
    # 18
    calcul['FRAIS_FIXES'].append(frais_fixe)

    inter = [calcul[l] for l in list(calcul.keys())[:-2]]
    val = list(map(sum, zip(*inter)))[0] * tva

    calcul['TVA'].append(ceil(val))

    inter = [calcul[l] for l in list(calcul.keys())[:-1]]
    val = list(map(sum, zip(*inter)))[0]

    calcul['TOTAL'].extend(["", val])

    calcul['INT_DEBITEURS_1'].insert(0, taux_int_1)
    calcul['INT_DEBITEURS_2'].insert(0, taux_int_2)
    calcul['INT_DEBITEURS_3'].insert(0, taux_int_3)
    calcul['COM_DE_MVTS'].insert(0, taux_com_mvts)
    calcul['COM_DE_DVERT'].insert(0, taux_com_dec)
    calcul['FRAIS_FIXES'].insert(0, "")
    calcul['TVA'].insert(0, tva)

    return calcul


# COMPUTATION FOR EPARGNE

def computation_first_table_epargne(datas, account, operations, int_epargne, date_deb):
    # Initialization
    cols = ['CPTABLE', 'VALEUR', 'LIBELLES', 'DEBIT_MVTS', 'CREDIT_MVTS', 'SOLDES', 'SOLDE_JOUR', 'jrs', 'DEBITS_NBR',
            'CREDIT_NBR', 'SOLDES_NBR', 'MVTS_13', 'MVTS_14']
    res_data = {col: [] for col in cols}

    comp_dec_epargne = 10_000_000 if int_epargne else 50_000_000

    # Initialization

    # First part
    temp_datas = datas.copy()

    date_valeur = temp_datas['Date de Valeur'].tolist()

    sold = int(account['solde_initial'])

    date_initiale = date_deb.replace(day=1) - timedelta(days=1)
    res_data['VALEUR'].append(date_initiale.strftime('%d/%m/%Y'))
    res_data['CPTABLE'].append("")
    res_data['LIBELLES'].append("SOLDE INITIAL")

    if sold < 0:
        res_data['DEBIT_MVTS'].append(-1 * sold)
        res_data['CREDIT_MVTS'].append(0)
    else:
        res_data['DEBIT_MVTS'].append(0)
        res_data['CREDIT_MVTS'].append(sold)

    res_data['SOLDES'].append(-res_data['DEBIT_MVTS'][-1] + res_data['CREDIT_MVTS'][-1])
    soldes = res_data['SOLDES'][-1]
    jrs = abs((date_initiale - date_valeur[0]).days)
    res_data['SOLDE_JOUR'].append(soldes if jrs != 0 else 0)
    res_data['jrs'].append(jrs)
    debit_nombre = -soldes * jrs if soldes < 0 else 0
    credit_nombre = soldes * jrs if soldes > 0 else 0
    res_data['DEBITS_NBR'].append(debit_nombre)
    res_data['CREDIT_NBR'].append(credit_nombre)
    soldes_nombre = soldes if (soldes > 0 and jrs > 0) else 0
    res_data['SOLDES_NBR'].append(soldes_nombre)

    mvt_13 = soldes_nombre * jrs if soldes_nombre <= comp_dec_epargne else comp_dec_epargne * jrs
    res_data['MVTS_13'].append(mvt_13)
    mvt_14 = credit_nombre - res_data['MVTS_13'][-1]
    res_data['MVTS_14'].append(mvt_14)

    j = 1
    l = len(date_valeur)
    # Loop and compute values

    libelles_pass = ["INT. CREDITEURS", "TAXE FRAIS FIXE", "PRELEVEMENT LIBERATOIRE", "FRAIS FIXE"]
    for i in range(len(date_valeur)):

        libelle = temp_datas.iloc[i]['Libellé Opération']
        # res = [lib in libelle for lib in libelles_pass]
        # if any(res):
        #     continue

        # 1 et 2
        date_cpt = temp_datas.iloc[i]['Date Comptable']
        date_val = date_valeur[i]

        res_data['CPTABLE'].append(date_cpt.strftime('%d/%m/%Y'))
        res_data['VALEUR'].append(date_val.strftime('%d/%m/%Y'))

        # 3
        res_data['LIBELLES'].append(libelle)

        # 4 & 5
        debit_mvt = 0
        credit_mvt = 0
        montant = temp_datas.iloc[i]['Montant']

        if temp_datas.iloc[i].Sens == "D":
            debit_mvt = montant
        else:
            credit_mvt = montant

        res_data['DEBIT_MVTS'].append(debit_mvt)
        res_data['CREDIT_MVTS'].append(credit_mvt)

        soldes += res_data['CREDIT_MVTS'][-1] - res_data['DEBIT_MVTS'][-1]
        res_data['SOLDES'].append(soldes)

        if j < l - 1:
            jrs = abs((date_valeur[j] - date_val).days)
        else:
            jrs = 0
        j = j + 1

        res_data['SOLDE_JOUR'].append(soldes if jrs != 0 else 0)
        res_data['jrs'].append(jrs)
        debit_nombre = -soldes * jrs if soldes < 0 else 0
        credit_nombre = soldes * jrs if soldes > 0 else 0
        res_data['DEBITS_NBR'].append(debit_nombre)
        res_data['CREDIT_NBR'].append(credit_nombre)
        soldes_nombre = soldes if (soldes > 0 and jrs > 0) else 0
        res_data['SOLDES_NBR'].append(soldes_nombre)

        soldes_nbr = res_data['SOLDES_NBR'][-1]

        # Check if account has a discover
        mvt_13 = soldes_nbr * jrs if soldes_nbr <= comp_dec_epargne else comp_dec_epargne * jrs
        res_data['MVTS_13'].append(mvt_13)

        mvt_14 = credit_nombre - res_data['MVTS_13'][-1]
        res_data['MVTS_14'].append(mvt_14)

    return res_data


def computation_second_table_epargne(res_data, options, int_epargne):
    # Get taux_interets_debiteurs
    taux_int_1 = float(options["taux_interet_inferieur"]) / 100
    taux_int_2 = float(options["taux_interet_superieur"]) / 100
    taux_ircm = float(options["taux_ircm"]) / 100
    tva = float(options["taux_tva"]) / 100
    frais_fixe = 0
    comp_dec_epargne = 10_000_000 if int_epargne else 50_000_000

    int_inf = 'INT_SUP <= {}'.format(comp_dec_epargne)
    int_sup = 'INT_SUP > {}'.format(comp_dec_epargne)

    cols_calcul = [int_inf, int_sup, 'IRCM', 'FRAIS_FIXES', 'TVA', 'TOTAL']

    calcul = {col: [] for col in cols_calcul}

    # # 14
    res = (sum(res_data['MVTS_13']) * taux_int_1) / 360
    calcul[int_inf].append(ceil(res))

    # 15
    res = (sum(res_data['MVTS_14']) * taux_int_2) / 360
    calcul[int_sup].append(ceil(res))

    # 15
    res = calcul[int_sup][-1] * taux_ircm
    calcul['IRCM'].append(0)

    # 18
    calcul['FRAIS_FIXES'].append(frais_fixe)

    inter = frais_fixe * tva

    calcul['TVA'].append(ceil(inter))

    inter = [calcul[l] for l in list(calcul.keys())[:-1]]
    val = list(map(sum, zip(*inter)))[0]

    calcul['TOTAL'].extend(["", val])

    calcul[int_inf].insert(0, taux_int_1)
    calcul[int_sup].insert(0, taux_int_2)
    calcul['IRCM'].insert(0, taux_ircm)
    calcul['FRAIS_FIXES'].insert(0, "")
    calcul['TVA'].insert(0, tva)

    return calcul


# END COMPUTATION EPARGNE

# Statistics
def get_statistics():
    pass


def whole_process(data_filter):
    result_data = computation_first_table(data_filter)
    compute = computation_first_table(result_data)

    return result_data, compute
