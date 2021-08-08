from django.shortcuts import render
from rest_framework import views
from rest_framework.parsers import BaseParser, MultiPartParser
from rest_framework.response import Response
from django.http.response import StreamingHttpResponse
import pandas as pd
import pathlib
from datetime import date, datetime, timedelta
from .models import *
from django.utils.timezone import utc, now
import re
from unidecode import unidecode
from rest_framework.decorators import api_view
from io import StringIO
from math import ceil
from json import load, dumps, loads
from rest_framework.permissions import IsAuthenticated
from django.core import serializers
from django.http import JsonResponse

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
def make_calcul(request):
    # Get data passed by request
    # We will compute all data separately

    # First get the last current historic

    # get all request datas  & latest historic
    datas = pd.DataFrame(request.data['accounts'])
    dates = request.data['period']

    type_account = request.data['type_account']

    save_history = Historic.objects.filter(user=request.user).latest('created_at').historic

    if save_history:
        save_history = loads(save_history)
        historic = pd.read_json(save_history['historic'])
    else:
        return Response(500)

    all_accounts = list(datas['num_compte'].unique())

    # filter by account

    date_deb = datetime.strptime(dates[0], "%Y-%m-%d")
    date_fin = datetime.strptime(dates[1], "%Y-%m-%d")
    historic = historic[historic['N° compte'].isin(all_accounts)]
    historic['Date Comptable'] = pd.to_datetime(historic['Date Comptable'])
    historic['Date de Valeur'] = pd.to_datetime(historic['Date de Valeur'])
    historic = historic[((date_deb <= historic['Date Comptable']) & (historic['Date Comptable'] <= date_fin))]
    historic = historic[((date_deb <= historic['Date de Valeur']) & (historic['Date de Valeur'] <= date_fin))]
    historic['N° compte'] = historic['N° compte'].astype('str')
    historic['N° compte'] = historic['N° compte'].str.zfill(11)

    # Type : conf or reg, Fusion: True or False
    if len(historic) == 0:
        return Response(500)

    dataframes = []
    if request.data['conf'] == "conf":

        for account in request.data["accounts"]:

            data_filtering = historic[historic['N° compte'] == account["num_compte"]]

            if len(data_filtering) == 0:
                return Response(500)

            # sort data by valeur date
            filter_datas = range_file(data_filtering)

            if type_account == "Courant":

                first = computation_first_table(filter_datas, account, request.data['type_account'])

                second = computation_second_table(pd.DataFrame(first), account, request.data['type_account'])

                # Adding ecar
                ecar = []
                col_datas = ['interet_0', 'interet_1', 'interet_2', 'com_mvt','com_dec','fraix_fixe','tva']

                ecar.append(second['INT_DEBITEURS_1'][1] - account['interet_0'])
                second['INT_DEBITEURS_1'].extend([account['interet_0'], ecar[-1]])

                ecar.append(second['INT_DEBITEURS_2'][1] - account['interet_1'])
                second['INT_DEBITEURS_2'].extend([account['interet_1'], ecar[-1]])

                ecar.append(second['INT_DEBITEURS_3'][1] - account['interet_2'])
                second['INT_DEBITEURS_3'].extend([account['interet_2'], ecar[-1]])

                ecar.append(second['COM_DE_MVTS'][1] - account['com_mvt'])
                second['COM_DE_MVTS'].extend([account['com_mvt'], ecar[-1]])

                ecar.append(second['COM_DE_DVERT'][1] - account['com_dec'])
                second['COM_DE_DVERT'].extend([account['com_dec'], ecar[-1]])

                ecar.append(second['FRAIS_FIXES'][1] - account['fraix_fixe'])
                second['FRAIS_FIXES'].extend([account['fraix_fixe'], ecar[-1]])

                ecar.append(second['TVA'][1] - account['tva'])
                second['TVA'].extend([account['tva'], ecar[-1]])

                second['TOTAL'].extend([sum([account[col] for col in col_datas]), sum(ecar)])

                new_first = [dict(zip(first, t)) for t in zip(*first.values())]

                new_second = []

                new_first.append({k: "" for k in list(first.keys())})
                new_first.append({k: "" for k in list(first.keys())})
                new_first.append({"SOLDES": "DESIGNATION", "SOLDE_JOUR": "TAUX", "jrs": "AGIOS", "DEBITS_NBR": "AMPLITUDE", "CREDIT_NBR": "ECART"})

                for i, key in enumerate(list(second.keys())):
                    part_dict = {"col_0": key, "id": i}
                    part_dict.update({"col_" + str(i+1): col for i, col in enumerate(second[key])})
                    new_second.append(part_dict)
                    res = {'SOLDES': key, "SOLDE_JOUR": second[key][0], "jrs": second[key][1],
                           "DEBITS_NBR": second[key][2], "CREDIT_NBR": second[key][3]}
                    new_first.append(res)

                dataframes.append({'first': new_first, 'account': account, "second": new_second})
            elif type_account == "Epargne":

                first = computation_first_table(filter_datas, account, request.data['type_account'])

                second = computation_second_table_epargne(pd.DataFrame(first), account, request.data['type_account'])

                ecar = []
                col_datas = ['INT_INF', 'INT_SUP', 'IRCM', 'fraix_fixe','tva']

                ecar.append(second['INT_INF'][1] - account['interet_inf'])
                second['INT_INF'].extend([account['interet_inf'], ecar[-1]])

                ecar.append(second['INT_SUP'][1] - account['interet_sup'])
                second['INT_SUP'].extend([account['interet_sup'], ecar[-1]])

                ecar.append(second['FRAIS_FIXES'][1] - account['frais_fixe'])
                second['FRAIS_FIXES'].extend([account['frais_fixe'], ecar[-1]])

                ecar.append(second['TVA'][1] - account['tva'])
                second['TVA'].extend([account['tva'], ecar])

                second['TOTAL'].extend([sum([account[col] for col in col_datas]), sum(ecar)])

                new_first = [dict(zip(first, t)) for t in zip(*first.values())]

                new_second = []

                new_first.append({k: "" for k in list(first.keys())})
                new_first.append({k: "" for k in list(first.keys())})
                new_first.append({"SOLDES": "DESIGNATION", "SOLDE_JOUR": "TAUX", "jrs": "AGIOS", "DEBITS_NBR": "AMPLITUDE", "CREDIT_NBR": "ECART"})

                # Rename second dict keys
                second['INTERETS <= 10 000 000'] = second.pop('INT_INF')
                second['INTERETS > 10 000 000'] = second.pop('INT_SUP')

                for i, key in enumerate(list(second.keys())):
                    part_dict = {"col_0": key, "id": i}
                    part_dict.update({"col_" + str(i+1): col for i, col in enumerate(second[key])})
                    new_second.append(part_dict)
                    res = {'SOLDES': key, "SOLDE_JOUR": second[key][0], "jrs": second[key][1],
                           "DEBITS_NBR": second[key][2], "CREDIT_NBR": second[key][3]}
                    new_first.append(res)

                dataframes.append({'first': new_first, 'account': account, "second": new_second})

    # Regularisation part
    elif request.data['conf'] == "reg":

        datas = pd.Dataframe(request.data['accounts'])

        date_deb = request.data['date_deb']
        date_fin = request.data['date_fin']
        operations = pd.DataFrame(request.data['operations'])
        type_account = request.data['type_account']

        # select corresponding history
        save_history = Historic.objects.filter(user=request.user).latest('created_at').historic

        if len(datas) == 0 or not save_history:
            return Response(500)

        all_accounts = list(datas['num_compte'].unique())

        historic = pd.DataFrame(save_history['historic'])

        # Filter by all values
        historic = historic[(historic['N° compte'].isin(all_accounts)) and (
            all((date_deb <= historic['Date Comptable'], historic['Date de Valeur'] <= date_fin)))]

    return Response({
        'data': dataframes
    })


@api_view(['POST'])
def get_infos(request):
    # Check con
    data = request.data

    # Define direction and account type
    direction = data['conf']
    type_account = data['type_account']

    # Steps: 1- select by config,
    # select:

    # Get all  infos base on history

    # Get latest history
    save_history = Historic.objects.filter(user=request.user).latest('created_at').historic

    if save_history:
        save_history = loads(save_history)
        historic = pd.read_json(save_history['historic'])
        accounts = pd.DataFrame(save_history['accounts'])
        accounts = accounts[accounts.type_compte == type_account]
        accounts = list(pd.DataFrame(accounts).T.to_dict().values())
        operations = pd.DataFrame(save_history['operations'])
    else:
        return Response(500)

    delta = list(Echelle.objects.filter(user=request.user).values())

    echelle_accounts = pd.DataFrame(list(Echelle.objects.filter(user=request.user).values('num_compte')))['num_compte'].unique()

    # loop through all unique accounts

    new_infos_account = []
    id = 0

    if type_account == "Epargne":

        for info_account in accounts:

            if info_account['num_compte'] not in echelle_accounts:
                continue

            # Initialization
            interet_inf = [TAUX_INT_EPARGNE, INITIAL_VALUE]
            interet_sup = [TAUX_INT_EPARGNE, INITIAL_VALUE]
            ircm = [TAUX_IRCM_EPARGNE, INITIAL_VALUE]
            tva = [TAUX_TVA, INITIAL_VALUE]
            frais_fixe = 2000
            autorisations = {}

            try:
                account_echelle = next(item for item in delta if item['num_compte'] == info_account['account'])
            except Exception as e:
                account_echelle = None

            if account_echelle is not None:

                info_account.update({"code_agence": account_echelle['code_agence']})

                # 1- Interets

                echelle_deb, echelle_cred = account_echelle['interets_debiteurs'], account_echelle[
                    'interets_crediteurs']

                # Intermediate fonction for interest
                def get_interets_epargne(interets):

                    taux_init = 0
                    int_inf = 0
                    int_sup = 0

                    for ind, item in enumerate(interets):
                        if ind == 0:
                            taux_init = item['taux']

                        val_interet = item['val']

                        if val_interet <= SEUIL_INT_INF:
                            int_inf += val_interet
                        else:
                            int_sup += val_interet

                    return taux_init, int_inf, int_sup

                if echelle_deb is not None:
                    res_deb = get_interets_epargne(echelle_deb)
                    interet_inf[0] = res_deb[0]
                    interet_inf[1] += res_deb[1]
                    interet_sup[1] += res_deb[2]

                if echelle_cred is not None:
                    res_cred = get_interets_epargne(echelle_cred)
                    interet_sup[0] = res_cred[0]
                    interet_sup[1] += res_cred[1]
                    interet_inf[1] += res_cred[2]

                # 2- Tva
                if account_echelle['tva'] is not None:
                    tva[0] = account_echelle['tva']['taux']
                    tva[1] = account_echelle['tva']['val']

                # 3- Ircm
                ircm[1] = ceil(interet_sup[1] * TAUX_IRCM_EPARGNE / 100)

                # 4- frais fixe
                if account_echelle['frais_fixe'] is not None:
                    frais_fixe = account_echelle['frais_fixe']

                # autorisations
                if account_echelle['autorisations'] is not None:
                    autorisations = account_echelle['autorisations']

            # Final step: Update the dictionnary
            info_account.update(autorisations)
            info_account.update(
                {'interet_inf': interet_inf[1], 'taux_interet_inf': interet_inf[0], 'interet_sup': interet_sup[1],
                 'taux_interet_sup': interet_sup[0], 'fraix_fixe': frais_fixe, 'tva': tva[1], 'taux_tva': tva[0],
                 'ircm': ircm[1], 'taux_ircm': ircm[0]})

            new_infos_account.append(info_account)

    elif type_account == "Courant":

        for info_account in accounts:

            if info_account['num_compte'] not in echelle_accounts:
                continue

            interets = [{'taux': 0, 'val': 0} for i in range(LEN_INTERET_DEBITEURS)]
            autorisations = {}
            com_mvt = {'taux': TAUX_COM_MVT, 'val': INITIAL_VALUE}
            com_dec = {'taux': TAUX_DEC, 'val': INITIAL_VALUE}
            tva = {'taux': TAUX_TVA, 'val': INITIAL_VALUE}
            frais_fixe = 5000
            solde_initial = 0
            info_account.update({"solde_initial": solde_initial, "id": id})
            id += 1

            try:
                account_echelle = next(item for item in delta if item['num_compte'] == info_account['num_compte'])
            except Exception as e:
                account_echelle = None

            if account_echelle is not None:

                info_account.update({"code_agence": account_echelle['code_agence']})

                # interet computing
                echelle_deb = account_echelle['interets_debiteurs']

                if echelle_deb is not None:
                    for i in range(len(echelle_deb)):
                        if i == 2:
                            break
                        interets[i].update(echelle_deb[i])

                # commissions
                if account_echelle["comission_mouvement"] is not None:
                    com_mvt.update(account_echelle["comission_mouvement"])

                if account_echelle["comission_decouvert"] is not None:
                    com_dec.update(account_echelle["comission_decouvert"])

                # tva
                if account_echelle['tva'] is not None:
                    tva.update(account_echelle['tva'])

                # frais fixes
                if account_echelle['frais_fixe'] is not None:
                    frais_fixe = account_echelle['frais_fixe']

                if account_echelle['autorisations'] is not None:
                    autorisations.update(account_echelle['autorisations'])

            # Update dict
            info_account.update({"interet_" + str(i): a['val'] for i, a in enumerate(interets)})
            info_account.update({"taux_interet_" + str(i): a['taux'] for i, a in enumerate(interets)})
            info_account.update(autorisations)
            info_account.update(
                {'fraix_fixe': frais_fixe, 'tva': tva['val'], 'taux_tva': tva['taux'], 'com_mvt': com_mvt['val'],
                 'taux_com_mvt': com_mvt['taux'],
                 'com_dec': com_dec['val'], 'taux_com_dec': com_dec['taux']})
            new_infos_account.append(info_account)

    else:
        return Response(500)
    return Response(new_infos_account)


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
        file_path = str(file) + "---" + str(datetime.now()).replace(":", "-")

        choice = request.data['choice']
       
       # Match corresponding choices
        if choice == "historique":
            
            try:
                datas = pd.read_csv(file, sep="|", header=None, low_memory=False)
                datas.rename(columns={0:"Date Comptable", 1:"Code Agence", 2:"N° Compte", 3: "Devise", 5:"Sens", 6:"Montant", 7:"Code Opération",8:"Libellé Opération", 10: "Date de Valeur"}, inplace=True)
                cols = ["Date Comptable", "Code Agence","N° Compte", "Devise","Sens","Montant","Code Opération","Libellé Opération","Date de Valeur"]
                
                # Will be drop later 
                datas.dropna(subset=cols, inplace=True)
                
                final_data = datas[cols]

                final_data = datas[cols].copy()

                # Fill values
                final_data['Date Comptable'] = pd.to_datetime(final_data['Date Comptable'], errors="ignore").dt.date
                final_data['Date de Valeur'] = pd.to_datetime(final_data['Date de Valeur'], errors="ignore").dt.date
                
                # Str columns
                for col in ["N° Compte", "Devise", "Sens", "Libellé Opération","Code Opération", "Code Agence", "Montant"]:
                    final_data[col] = final_data[col].astype(str) 
                    
                # Processing Amount 
                final_data['Montant'] = final_data['Montant'].apply(lambda x: int(x.split(",")[0]))
                comptes = pd.DataFrame({"N° Compte":final_data['N° Compte'].unique()})
                comptes['Type de Compte'] = final_data['N° Compte'].apply(lambda x: "Epargne" if x[-4:-1] == "110" else "Courant")

                path_histo = PATH_HISTORIQUE + file_path 
                path_operations = PATH_OPERATIONS + file_path
                path_compte = PATH_COMPTE + file_path 

                # Processing operations
                operations = pd.DataFrame({"Code Opération": final_data['Code Opération'].unique()})
                operations['Code Opération'] = operations['Code Opération'].apply(fill_operation)

                # save datas 
                # Update latest record
                try:
                   modify_last_record(choice)
                except File.DoesNotExist:
                    pass

                options = {"date_inf": final_data['Date Comptable'].min(), "date_sup": final_data['Date Comptable'].max(), "len": len(final_data)}

                save_file(request.user, file_path, choice, options)

                final_data.to_csv(path_histo, index=False, compression="gzip")
                comptes.to_csv(path_compte, index=False, compression="gzip")
                operations.to_csv(path_operations, index=False, compression="gzip")

            except Exception as e:
                print(e)
                return JsonResponse({"message": "Le fichier {} ne respecte pas le format exigé - voir le guide".format(file)}, status=500)


        elif choice == "solde":

            # Loading all initial solds inside the data base
            try:
                
                str_cols = ['Code Agence', 'Devise', 'N° Compte', 'Mois', "Solde"]
                dtypes = {col: str for col in str_cols}
                datas_soldes = pd.read_csv(file, sep="|", dtype=dtypes, parse_dates=['Date Solde', 'Date Mois Suivant', 'Date Mois M+1'])
                datas_soldes.rename(columns={0:"Code Agence", 1:"Devise", 2:"N° Compte", 3: "Année", 4:"Mois", 6:"Date Solde", 
                7:"Solde", 8:"Date Mois Suivant"}, inplace=True)
                datas_soldes.sort_values(by='Date Solde', ascending=False, inplace=True)
                datas_soldes.drop_duplicates(subset='N° Compte', keep='first', inplace=True)
                datas_soldes['Solde'] = datas_soldes['Solde'].apply(lambda x: int(x.split(",")[0]))
                datas_soldes = datas_soldes[['N° Compte', 'Solde', 'Date Solde', 'Date Mois Suivant', 'Mois']]
            except Exception as e:
                return JsonResponse({"message": "Le fichier {} ne respecte pas le format exigé - voir le guide".format(file)}, status=500)

            if datas_soldes.isnull().sum().sum() != 0:
                return JsonResponse({"message": "Le fichier {} contient des valeurs nulles".format(file)}, status=500)

            # save soldes datas on disk and save it in database
            try:
                path_solde = PATH_SOLDE + file_path
                datas_soldes.to_csv(path_solde, index=False, compression="gzip")

                # Update latest record
                try:
                   modify_last_record(choice)
                except File.DoesNotExist:
                    pass

                # Save new added file
                options = {"date_inf": datas_soldes['Date Comptable'].min(), "date_sup": datas_soldes['Date Comptable'].max(), "len": len(datas_soldes)}
                save_file(request.user, file_path, choice, options)

            except Exception as e:
                return JsonResponse({"message": "Une erreur est survenue lors de l'enregistrement du fichier {}".format(file)}, status=500)

        elif choice == "autorisation":
            
            try:
                datas_autorisations = pd.read_csv(file, sep="|", header=None)
                datas_autorisations.rename(columns={0:"Code Agence", 1:"N° Compte", 2: "Clé", 3:"Date Mise en Place", 4:"Date de fin", 5:"Montant",6:"Taux", 10: "Date de Valeur"}, inplace=True)

                path_auto =  PATH_AUTORISATION + file_path

                datas_autorisations.to_csv(PATH_HISTORIQUE, index=False, compression="gzip")

                try:
                   modify_last_record(choice)
                except File.DoesNotExist:
                    pass

                # Save new added file
                options = {"date_inf": datas_autorisations['Date Mise en Place'].min(), "date_sup": datas_autorisations['Date de fin'].max(), "len": len(datas_autorisations)}
                save_file(request.user, file_path, choice)

            except:
                return JsonResponse({"message": "Une erreur est survenue lors de l'enregistrement du fichier {}".format(file)}, status=500)

        elif choice == "journal":
            # We'll do stuff later
            pass


        return Response(204)



def fill_operation(code_operation):

    libelle_operation = "No libelle"
    with open(CODES_PATH, "r") as file:
        codes = load(file)
        # Try to get his corresponding code
        try:
            libelle_operation = codes[code_operation]
        except Exception as e:
            print(e)
    
    return libelle_operation

    

# Modify last record 
def modify_last_record(choice):
    prev = File.objects.get(active_file=True, file_type=choice)
    prev.active_file = False
    prev.save()

def save_file(user, file_path, choice, options):
    new_file = File()
    new_file.user = user
    new_file.file_path = file_path
    new_file.file_type = choice
    new_file.date_inf = options['date_inf']
    new_file.date_inf = options['date_sup']
    new_file.longueur = options['len']
    new_file.active_file = True
    new_file.save()


# Load datas excel file
def load_data_excel(data_excel, current_user, file):
    # Delete all rows on new uploading

    accounts = []

    operations = (data_excel['Code Opération'].astype(str)).unique().tolist()

    all_accounts = data_excel['N° compte'].unique().tolist()
    # Process accounts
    for account in all_accounts:

        type_account = "Courant"

        datas = data_excel[data_excel['N° compte'] == account]
        # Get all intitule and operation code
        intitule = datas['Intitulé compte'].mode()[0]
        codes_operation = datas['Code Opération'].unique().tolist()

        if "epargne" in unidecode(intitule.lower()) or "100" in codes_operation:
            type_account = "Epargne"

        accounts.append({"num_compte": account, "intitule": intitule, "type_compte": type_account})

    # Save operations
    if len(operations) != 0:

        operations = []
        libelle_operation = "No libelle"
        with open(CODES_PATH, "r") as file:
            codes = load(file)
        for op in operations:

            # Try to get his corresponding code
            try:
                libelle_operation = codes[op]
            except Exception as e:
                print(e)
            operations.append({"code_operation": op, "libelle_operation": libelle_operation})

        file.close()

    # save historic
    new_hist = Historic()
    data_excel['Date Comptable'] = data_excel['Date Comptable'].astype('str')
    data_excel['Date de Valeur'] = data_excel['Date de Valeur'].astype('str')

    historic_part = data_excel.to_json()
    formatted_historic = {"historic": historic_part, "accounts": accounts, "operations": operations}
    new_hist.historic = dumps(formatted_historic)
    new_hist.user = current_user

    try:
        new_hist.save()
    except Exception as e:
        return JsonResponse({"message": "Erreur d'enregistrement du fichier {} ".format(file)}, status=500)


# load datas txt file
def load_data_txt(datas_txt, current_user, file):
    # code_agence , account_number, amount, dates = None, None, None, None

    auto_part = 40
    stri = datas_txt.tail(auto_part).values.tolist()
    string_datas = " ".join(stri)

    global datas
    datas = string_datas


    def get_value(colname, position, sep=" "):
        """
        :param: column name, position
        :return: corresponded value
        """
        value = re.search(regex_dict[colname], datas).group().split(sep)[position]
        return value

    def get_interet(string, pos_char=-1, sep="."):

        if isinstance(string, list):
            string = string[0]

        initial = string.split()[pos_char]

        value = None

        if sep == ".":
            value = int(initial.replace(sep, ""))
        else:
            value = float(initial.replace(sep, "."))

        return value

    reg_numb = "( )*(-)?([0-9\.,]+)(\d)+( )*[(TVA)(%)]*"
    date_reg = '(\d\d)[-/](\d\d)[-/](\d\d(?:\d\d)?)'
    regex_dict = {
        'code': '\d{4} -',
        'account': 'XAF-\d{11}-\d{2}',
        'dates': '(\d\d)[-/](\d\d)[-/](\d\d(?:\d\d)?)',
        'amount': '([0-9]+\.)+(\d{3}) XAF',
        'taxe_frais': 'TAXE/FRAIS{} ( )* TVA '.format(reg_numb),
        'com_mvt': ' COMMISSION DE MOUVEMENT({})+'.format(reg_numb),
        'com_dec': ' COMMISSION/PLUS FORT DECOUVERT({})+'.format(reg_numb),
        'int_debit': ' INTERETS DEBITEURS({})+'.format(reg_numb),
        'int_credit': ' INTERETS CREDITEURS({})+'.format(reg_numb),
        'frais_fixe': 'FRAIS FIXES{}'.format(reg_numb),
        'net_deb': 'NET A DEBITER{}'.format(reg_numb),
        'solde_val': 'SOLDE EN VALEUR APRES AGIOS{}'.format(reg_numb),
        'tva': '(TAXE/INTERETS DEBITEURS|TAXE/COMM. PLUS FORT DECOUVERT|TAXE/COMMISSION DE MOUVEMENT|TAXE/FRAIS)({})+( )*'.format(
            reg_numb),
        'ircm': 'PRELEVEMENT LIBERATOIRE a compter du ( )* {}( )*({})+'.format(date_reg, reg_numb)
    }

    # Try to fill all values
    code_agence, account_number, date_deb_arrete, date_fin_arrete, frais_fixe, ircm, interets_debiteurs, \
    interets_crediteurs, tva, comission_mouvement, comission_decouvert, date_deb_arrete, date_fin_arrete, autorisations = [None] * 14

    new_ech = Echelle()

    try:
        new_dates = []
        code_agence = get_value('code', 0)
        account_number = get_value('account', 1, "-")
        dates = re.findall(regex_dict['dates'], datas)
        dates = dates[:-1] if len(dates) % 2 != 0 else dates

        # get all dates
        for single_date in dates:
            res = [int(num) for num in single_date[::-1]]
            new_date = date(res[0], res[1], res[2])
            new_dates.append(new_date)

        date_deb_arrete = new_dates[0]
        date_fin_arrete = new_dates[1]

        frais_fixe = int(re.search(regex_dict['frais_fixe'], datas).group().split()[-1].replace(".", ""))

    except Exception as e:
        print(e)

    # Autorisations

    if new_dates and len(new_dates) > 2:
        try:
            montants = [int(match.group().replace("XAF", "").replace(".", "")) for match in
                        re.finditer(regex_dict['amount'], datas)]
            j = 0
            part_autorisations = []
            for i in range(0, len(new_dates[2:]), 2):
                part_autorisations.append({'montant': montants[j], 'debut_autorisation': new_dates[i + 2],
                                           'fin_autorisation': new_dates[i + 3]})
                j += 1
            if len(part_autorisations) != 0:
                autos = pd.DataFrame(part_autorisations).sort_values(by='debut_autorisation', ascending=False)
                autos.debut_autorisation = autos.debut_autorisation.astype('str')
                autos.fin_autorisation = autos.fin_autorisation.astype('str')
                autos.montant = autos.montant.astype('int')
                autorisations = autos.iloc[0].to_dict()
                autorisations['montant'] = int(autorisations['montant'])

        except Exception as e:
            print(e)

    # Interets DEBITEURS
    try:
        all_int_debiteurs = [match.group() for match in re.finditer(regex_dict['int_debit'], datas)]
        interets_debiteurs = []
        for i, interet in enumerate(all_int_debiteurs):
            val_int = get_interet(interet)
            taxe_int = get_interet(interet, pos_char=-2, sep=",")
            interets_debiteurs.append({'val': val_int, 'taux': taxe_int})

    except Exception as e:
        print(e)

    # Interets CREDITEURS
    try:
        all_int_crediteurs = [match.group() for match in re.finditer(regex_dict['int_credit'], datas)]
        interets_crediteurs = []
        for i, interet in enumerate(all_int_crediteurs):
            val_int = get_interet(interet)
            taxe_int = get_interet(interet, pos_char=-2, sep=",")
            interets_crediteurs.append({'val': val_int, 'taux': taxe_int})
    except Exception as e:
        print(e)

    # IRCM
    try:
        all_ircm = re.search(regex_dict['ircm'],
                             string_datas.translate(str.maketrans({val: ' ' for val in ['\n', '!', '-']}))).group(
            0).strip().split()
        ircm = {'val': int(all_ircm[-1].replace('.', '')), 'taux': float(all_ircm[-2].replace(',', '.'))}
    except Exception as e:
        print(e)

    # Commission mouvement
    try:
        res_mvt = [re.search(regex_dict['com_mvt'], datas).group()]
        taxe_com_mvt = get_interet(res_mvt, pos_char=-2, sep=",")
        com_mvt = get_interet(res_mvt)
        comission_mouvement = {'val': com_mvt, 'taux': taxe_com_mvt}
    except Exception as e:
        print(e)

    # Commission découvert
    try:
        res_dec = [re.search(regex_dict['com_dec'], datas).group()]
        taxe_com_dec = get_interet(res_dec, pos_char=-2, sep=",")
        com_dec = get_interet(res_dec)
        comission_decouvert = {'val': com_dec, 'taux': taxe_com_dec}
    except Exception as e:
        print(e)

    # TVA
    try:
        all_tva = [match.group() for match in re.finditer(regex_dict['tva'], datas)]
        taux_tva = get_interet(all_tva, pos_char=-3, sep=",")

        taxes_tva = [get_interet(string_tva, pos_char=-5) for string_tva in all_tva]
        val_tva = ceil(sum(taxes_tva) * (taux_tva / 100))
        tva = {}
        tva['val'] = val_tva
        tva['taux'] = taux_tva

    except Exception as e:
        print(e)

    if None not in [code_agence, account_number, date_deb_arrete, date_fin_arrete]:
        new_ech.user = current_user
        new_ech.code_agence = code_agence
        new_ech.num_compte = account_number
        new_ech.date_deb_arrete = date_deb_arrete
        new_ech.date_fin_arrete = date_fin_arrete
        new_ech.frais_fixe = frais_fixe
        new_ech.autorisations = autorisations
        new_ech.interets_debiteurs = interets_debiteurs
        new_ech.interets_crediteurs = interets_crediteurs
        new_ech.ircm = ircm
        new_ech.comission_mouvement = comission_mouvement
        new_ech.comission_decouvert = comission_decouvert
        new_ech.tva = tva
        try:
            new_ech.save()
        except Exception as e:
            print(e)
    else:
        return JsonResponse({"message": "Le fichier {} ne contient pas les informations de base requises".format(file)}, status=500)


# Processing functions
def range_file(data_excel):
    res_filter_date = data_excel.copy()

    res_filter_date['index'] = res_filter_date.index
    res_filter_date = res_filter_date.sort_values(by=['Date de Valeur', 'index'])
    res_filter_date = res_filter_date.drop(columns='index')

    return res_filter_date


# ----- System conform computation -----#

# Computation function for courant
def computation_first_table(datas, account, type_account):
    # Initialization
    cols = ['CPTABLE', 'VALEUR', 'LIBELLES', 'DEBIT_MVTS', 'CREDIT_MVTS', 'SOLDES', 'SOLDE_JOUR', 'jrs', 'DEBITS_NBR',
            'CREDIT_NBR', 'SOLDES_NBR', 'MVTS_13', 'MVTS_14']
    res_data = {col: [] for col in cols}

    # Initialization

    # Computation part

    # First part
    res_filter_date = datas.copy()

    # range by date value
    res_filter_date['index'] = res_filter_date.index
    res_filter_date = res_filter_date.sort_values(by=['Date de Valeur', 'index'])
    res_filter_date = res_filter_date.drop(columns='index')
    temp_datas = res_filter_date.copy()
    date_valeur = temp_datas['Date de Valeur'].tolist()

    sold = int(account['solde_initial'])
    j = 1

    date_initiale = date_valeur[0].replace(day=1) - timedelta(days=1)
    res_data['VALEUR'].append(date_initiale.strftime('%d/%m/%Y'))
    res_data['CPTABLE'].append("")
    res_data['LIBELLES'].append("SOLDE INITIAL")

    if sold <= 0:
        res_data['DEBIT_MVTS'].append(sold)
        res_data['CREDIT_MVTS'].append(0)
    else:
        res_data['DEBIT_MVTS'].append(0)
        res_data['CREDIT_MVTS'].append(sold)

    res_data['SOLDES'].append(-res_data['DEBIT_MVTS'][-1] + res_data['CREDIT_MVTS'][-1])
    soldes = res_data['SOLDES'][-1]
    jrs = abs((date_valeur[0] - date_initiale).days)
    res_data['SOLDE_JOUR'].append(soldes if jrs != 0 else 0)
    res_data['jrs'].append(jrs)
    debit_nombre = -soldes * jrs if soldes < 0 else 0
    credit_nombre = soldes * jrs if soldes > 0 else 0
    res_data['DEBITS_NBR'].append(debit_nombre)
    res_data['CREDIT_NBR'].append(credit_nombre)
    soldes_nombre = -soldes if soldes < 0 else 0
    res_data['SOLDES_NBR'].append(soldes_nombre)
    soldes_nbr = res_data['SOLDES_NBR'][-1]

    if "montant" in list(account.keys()):
        deb_autorisation = datetime.strptime(account['debut_autorisation'], "%Y-%m-%d")
        fin_autorisation = datetime.strptime(account['fin_autorisation'], "%Y-%m-%d")
        if deb_autorisation <= date_initiale <= fin_autorisation:
            mvt_13 = soldes_nbr * jrs if soldes_nbr <= account['montant'] else account['montant'] * jrs
            mvt_14 = debit_nombre - mvt_13

            res_data['MVTS_13'].append(mvt_13)
            res_data['MVTS_14'].append(mvt_14)
        else:
            res_data['MVTS_13'].append(0)
            res_data['MVTS_14'].append(0)
    else:
        res_data['MVTS_13'].append(0)
        res_data['MVTS_14'].append(0)

    j = 1
    l = len(date_valeur)
    # Loop and compute values
    for i in range(len(date_valeur)):

        # 1 et 2
        date_cpt = temp_datas.iloc[i]['Date Comptable']
        date_val = date_valeur[i]

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
        soldes_nombre = -soldes if soldes < 0 else 0

        res_data['SOLDES_NBR'].append(soldes_nombre)
        soldes_nbr = res_data['SOLDES_NBR'][-1]

        # Check if account has a discover
        if "montant" in list(account.keys()):
            deb_autorisation = datetime.strptime(account['debut_autorisation'], "%Y-%m-%d")
            fin_autorisation = datetime.strptime(account['fin_autorisation'], "%Y-%m-%d")
            if deb_autorisation <= date_initiale <= fin_autorisation:
                mvt_13 = soldes_nbr * jrs if soldes_nbr <= account['montant'] else account['montant'] * jrs
                mvt_14 = debit_nombre - mvt_13

                res_data['MVTS_13'].append(mvt_13)
                res_data['MVTS_14'].append(mvt_14)
            else:
                res_data['MVTS_13'].append(0)
                res_data['MVTS_14'].append(0)
        else:
            res_data['MVTS_13'].append(0)
            res_data['MVTS_14'].append(0)

    return res_data


def computation_second_table(res_data, account, type_account):

    # Get taux_interets_debiteurs
    taux_int_1 = account["taux_interet_0"] / 100
    taux_int_2 = account["taux_interet_1"] / 100
    taux_int_3 = account["taux_interet_2"] / 100
    taux_com_mvts = account["taux_com_mvt"] / 100
    taux_com_dec = account["taux_com_dec"] / 100
    tva = account["taux_tva"] / 100
    frais_fixe = 5000

    cols_calcul = ['INT_DEBITEURS_1', 'INT_DEBITEURS_2', 'INT_DEBITEURS_3', 'COM_DE_MVTS', 'COM_DE_DVERT',
                   'FRAIS_FIXES', 'TVA', 'TOTAL']
    calcul = {col: [] for col in cols_calcul}

    # # 14
    res = (sum(res_data['MVTS_13']) * taux_int_1) / 360
    calcul['INT_DEBITEURS_1'].append(int(res))

    # 15
    res = (sum(res_data['MVTS_14']) * taux_int_2) / 360
    calcul['INT_DEBITEURS_2'].append(int(res))

    res = (sum(res_data['MVTS_14']) * taux_int_3) / 360
    calcul['INT_DEBITEURS_3'].append(int(res))

    # 16
    seuil = 5000 if type_account == 'Epargne' else 2000

    int_sum = sum(res_data['DEBIT_MVTS'][1:]) * taux_com_mvts

    res = seuil if int_sum < seuil else int_sum
    calcul['COM_DE_MVTS'].append(ceil(res))

    # 17
    total_plus_fort = min(res_data['SOLDE_JOUR'])
    res = 0 if total_plus_fort >= 0 else -total_plus_fort * taux_com_dec
    calcul['COM_DE_DVERT'].append(ceil(res))

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

def computation_second_table_epargne(res_data, account, type_account):

    # Get taux_interets_debiteurs
    taux_int_1 = account["taux_interet_inf"] / 100
    taux_int_2 = account["taux_interet_sup"] / 100
    taux_ircm = account["ircm"] / 100
    tva = account["taux_tva"]
    frais_fixe = 2000

    cols_calcul = ['INT_DEBITEURS_1', 'INT_DEBITEURS_2', 'INT_DEBITEURS_3', 'COM_DE_MVTS', 'COM_DE_DVERT',
                   'FRAIS_FIXES', 'TVA', 'TOTAL']
    calcul = {col: [] for col in cols_calcul}

    # # 14
    res = (sum(res_data['MVTS_13']) * taux_int_1) / 360
    calcul['INT_INF'].append(int(res))

    # 15
    res = (sum(res_data['MVTS_14']) * taux_int_2) / 360
    calcul['INT_SUP'].append(int(res))

    # 15
    res = calcul['INT_SUP'][-1] * taux_ircm
    calcul['IRCM'].append(int(res))

    # 18
    calcul['FRAIS_FIXES'].append(frais_fixe)

    inter = frais_fixe * tva

    calcul['TVA'].append(ceil(inter))

    inter = [calcul[l] for l in list(calcul.keys())[:-1]]
    val = list(map(sum, zip(*inter)))[0]

    calcul['TOTAL'].extend(["", val])

    calcul['INT_INF'].insert(0, taux_int_1)
    calcul['INT_SUP'].insert(0, taux_int_2)
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
