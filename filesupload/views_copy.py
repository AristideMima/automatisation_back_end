from django.shortcuts import render
from rest_framework import views
from rest_framework.parsers import BaseParser, MultiPartParser
from rest_framework.response import Response
from django.http.response import StreamingHttpResponse
import pandas as pd
import pathlib
from datetime import date, datetime, timedelta
from pyexcel_xlsx import get_data
from .models import *
from django.utils.timezone import utc, now
import re
from unidecode import unidecode
from rest_framework.decorators import api_view
from .models import Historique
from io import StringIO
from math import ceil
from json import load

# Create your views here.

# class FileParser(BaseParser):
#     """
#         Class based custom parser
#     """
#
#     media_type = 'text/plain'
#
#     def parse(self, stream, media_type=None, parser_context=None):
#
#         return stream.read()

global regex_dict

regex_dict = {
    'excel': '[(*.xls)(xlsx]'
}

CODES_PATH = "static/libelle_codes.json"


@api_view(['POST'])
def make_calcul(request):
    # Get data passed by request
    # We will compute all data separately

    # Load latest history for computation
    # Slect

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
                col_datas = ['interet_0', 'interet_1', 'interet_2', 'com_mvt', 'com_dec', 'fraix_fixe', 'tva']

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
                new_first.append(
                    {"SOLDES": "DESIGNATION", "SOLDE_JOUR": "TAUX", "jrs": "AGIOS", "DEBITS_NBR": "AMPLITUDE",
                     "CREDIT_NBR": "ECART"})

                for i, key in enumerate(list(second.keys())):
                    part_dict = {"col_0": key, "id": i}
                    part_dict.update({"col_" + str(i + 1): col for i, col in enumerate(second[key])})
                    new_second.append(part_dict)
                    res = {'SOLDES': key, "SOLDE_JOUR": second[key][0], "jrs": second[key][1],
                           "DEBITS_NBR": second[key][2], "CREDIT_NBR": second[key][3]}
                    new_first.append(res)

                dataframes.append({'first': new_first, 'account': account, "second": new_second})
            elif type_account == "Epargne":

                first = computation_first_table(filter_datas, account, request.data['type_account'])

                second = computation_second_table_epargne(pd.DataFrame(first), account, request.data['type_account'])

                ecar = []
                col_datas = ['INT_INF', 'INT_SUP', 'IRCM', 'fraix_fixe', 'tva']

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
                new_first.append(
                    {"SOLDES": "DESIGNATION", "SOLDE_JOUR": "TAUX", "jrs": "AGIOS", "DEBITS_NBR": "AMPLITUDE",
                     "CREDIT_NBR": "ECART"})

                # Rename second dict keys
                second['INTERETS <= 10 000 000'] = second.pop('INT_INF')
                second['INTERETS > 10 000 000'] = second.pop('INT_SUP')

                for i, key in enumerate(list(second.keys())):
                    part_dict = {"col_0": key, "id": i}
                    part_dict.update({"col_" + str(i + 1): col for i, col in enumerate(second[key])})
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
    direction = "left"

    if data['conf'] != "conf":
        direction = "right"

    # Get all  infos base on history
    comptes = pd.DataFrame(list(Compte.objects.all().values()))
    delta = pd.DataFrame(list(Delta.objects.all().values()))

    if len(comptes) != 0:
        result = comptes.copy()
        if len(delta) != 0:
            result = delta.merge(comptes, on="num_compte", how="right")
            result.date_deb_autorisation = result.date_deb_autorisation.dt.strftime('%d/%m/%Y')
            result.date_fin_autorisation = result.date_fin_autorisation.dt.strftime('%d/%m/%Y')
            # result['period'] = result[['date_deb_autorisation', 'date_fin_autorisation']].agg(" - ".join, axis=1)

        result['solde_initial'] = 0
        result['key'] = result.index.tolist()

        return Response(result.T.to_dict().values())

    return Response([{}])


class FileUpload(views.APIView):
    """
        Class based file upload
    """
    parser_classes = [MultiPartParser]

    # file upload function
    def put(self, request, format=None):

        files = request.FILES.getlist('files[]')

        if len(files) == 0:
            return Response(500)

        for file in files:

            print(pathlib.Path(str(file)).suffix)

            if file:
                if pathlib.Path(str(file)).suffix in [".xls", ".xlsx"]:

                    print(file)

                    cols_str = ['Code Agence', 'Référence lettrage', 'chapitre', 'N° compte', 'Code Opération']
                    cols_dates = ['Date Comptable', 'Date de Valeur']
                    data_excel = pd.read_excel(file, skiprows=2, dtype={val: str for val in cols_str},
                                               parse_dates=cols_dates, dayfirst=True)

                    # data_excel.drop(columns=['Unnamed: 0'], inplace=True)

                    load_data_excel(data_excel.copy())

                else:
                    pass
                    data_excel = pd.read_csv(file, sep='\n', header=None, squeeze=True)
                    load_data_txt(data_excel.copy())

        return Response(204)


# Load datas excel file
def load_data_excel(data_excel):
    # Delete all rows on new uploading
    Historique.objects.all().delete()
    Compte.objects.all().delete()
    Operation.objects.all().delete()

    accounts = {}
    operations = (data_excel['Code Opération'].astype(str)).unique().tolist()

    all_accounts = data_excel['N° compte'].unique().tolist()

    for account in all_accounts:

        if account not in list(accounts.keys()):

            accounts[account] = "Courant"

            datas = data_excel[data_excel['N° compte'] == account]
            # Get all intitule and operation code
            intitule = datas['Intitulé compte'].mode()[0]
            codes_operation = datas['Code Opération'].unique().tolist()

            if "epargne" in unidecode(intitule.lower()) or "100" in codes_operation:
                accounts[account] = "Epargne"

            compte = Compte()
            compte.num_compte = account
            compte.intitule_compte = intitule
            compte.type_account = accounts[account]

            try:
                compte.save()
            except Exception as e:
                print(e)

    # Get account type of all accounts
    for i in range(len(data_excel)):

        data = data_excel.iloc[i]

        hist = Historique()

        hist.code_agence = data['Code Agence']
        hist.date_comptable = data['Date Comptable']
        hist.date_valeur = data['Date de Valeur']
        hist.num_compte = data['N° compte']
        hist.intitule_compte = data['Intitulé compte']
        hist.libelle_operation = data['Libellé Opération']
        hist.code_operation = data['Code Opération']
        hist.sens = data['Sens']
        hist.montant = data['Montant']

        # operations.add(hist.code_operation)

        try:
            hist.save()

        except Exception as e:
            print(e)

    # Save operations
    if len(operations) != 0:

        with open(CODES_PATH, "r") as file:
            codes = load(file)

        for op in operations:
            operation = Operation()
            operation.code_operation = op

            # Try to get his corresponding code
            try:
                operation.libelle_operation = codes[op]
            except Exception as e:
                print(e)

            try:
                operation.save()
            except Exception as e:
                print(e)

        file.close()


# load datas txt file
def load_data_txt(data_txt):
    # code_agence , account_number, amount, dates = None, None, None, None
    code_agence, account_number, amount, frais_fixe, com_plus_dec, com_mvt, int_1, int_2, taxe_int_1, taxe_int_2, taxe_com_plus_dec, taxe_com_mvt, taux_tva, tva, net_deb, solde_val, dates = [
                                                                                                                                                                                                  None] * 17

    auto_part = 30
    stri = data_txt.tail(auto_part).values.tolist()
    string_datas = " ".join(stri)

    reg_numb = "( )*(-)?([0-9\.,]+)(\d)+( )*[(TVA)(%)]*"
    regex_dict = {
        'code': '\d{4} -',
        'account': 'XAF-\d{11}-\d{2}',
        'dates': '(\d\d)[-/](\d\d)[-/](\d\d(?:\d\d)?)',
        'amount': '([0-9]+\.)+(\d{3}) XAF',
        'taxe_frais': 'TAXE/FRAIS{} ( )* TVA '.format(reg_numb),
        'taxe_com_mvt': 'TAXE/COMMISSION DE MOUVEMENT{}'.format(reg_numb),
        'com_mvt': 'COMMISSION DE MOUVEMENT({})+'.format(reg_numb),
        'com_dec': ' COMMISSION/PLUS FORT DECOUVERT({})+'.format(reg_numb),
        'int_debit': ' INTERETS DEBITEURS({})+'.format(reg_numb),
        'frais_fixe': 'FRAIS FIXES{}'.format(reg_numb),
        'net_deb': 'NET A DEBITER{}'.format(reg_numb),
        'solde_val': 'SOLDE EN VALEUR APRES AGIOS{}'.format(reg_numb),
        'tva': '(TAXE/INTERETS DEBITEURS|TAXE/COMM. PLUS FORT DECOUVERT|TAXE/COMMISSION DE MOUVEMENT|TAXE/FRAIS)({})+( )*'.format(
            reg_numb)
    }

    datas = string_datas

    # Helper functions definition
    def get_value(colname, position, sep=" "):
        """
        :param: column name, position
        :return: corresponded value
        """
        value = re.search(regex_dict[colname], datas).group().split(sep)[position]
        return value

    def get_interet(string_list, pos_string=0, pos_char=-1, sep="."):

        initial = string_list[pos_string].split()[pos_char]

        value = None

        if sep == ".":
            value = int(initial.replace(sep, ""))
        else:
            value = float(initial.replace(sep, "."))

        return value

    try:
        code_agence = get_value('code', 0)
        account_number = get_value('account', 1, "-")
        amount = int(get_value('amount', 0).replace(".", ""))

        frais_fixe = int(re.search(regex_dict['frais_fixe'], datas).group().split()[-1].replace(".", ""))
        dates = re.findall(regex_dict['dates'], datas)

        interets = [match.group() for match in re.finditer(regex_dict['int_debit'], datas)]
        int_1 = get_interet(interets)
        taxe_int_1 = get_interet(interets, pos_char=-2, sep=",")

        if len(interets) == 2:
            int_2 = get_interet(interets, 1)
            taxe_int_2 = get_interet(interets, pos_string=1, pos_char=-2, sep=",")
        else:
            int_2 = 0
            taxe_int_2 = 0

        res_plus_dec = [re.search(regex_dict['com_dec'], datas).group()]
        taxe_com_plus_dec = get_interet(res_plus_dec, pos_char=-2, sep=",")
        com_plus_dec = get_interet(res_plus_dec)

        res_mvt = [re.search(regex_dict['com_mvt'], datas).group()]
        taxe_com_mvt = get_interet(res_mvt, pos_char=-2, sep=",")
        com_mvt = get_interet(res_mvt)

        all_tva = [match.group() for match in re.finditer(regex_dict['tva'], datas)]
        taux_tva = get_interet(all_tva, pos_char=-3, sep=",")

        # taxes = [get_interet(all_tva, i) for i in range(4)]
        tva = ceil((int_1 + int_2 + com_mvt + com_plus_dec + frais_fixe) * (taux_tva / 100))

        net_deb = int(re.search(regex_dict['net_deb'], datas).group().split()[-1].replace(".", ""))

        solde_val = int(re.search(regex_dict['solde_val'], datas).group().split()[-1].replace(".", ""))

    except Exception as e:
        print(e)
    l = [code_agence, account_number, amount, frais_fixe, int_1, int_2, taxe_int_1, taxe_int_2,
         taxe_com_plus_dec, taxe_com_mvt, taux_tva, tva, net_deb, solde_val, dates]
    if None in l:
        print(l)
        return Response(500)
    else:
        arrete = Delta()
        # dates conversion
        new_dates = []
        for single_date in dates:
            res = [int(num) for num in single_date[::-1]]
            new_date = datetime(res[0], res[1], res[2])
            new_dates.append(new_date)

        arrete.code_agence = code_agence
        arrete.num_compte = account_number
        arrete.montant = amount
        arrete.interet_debiteur_1 = int_1
        arrete.interet_debiteur_2 = int_2
        arrete.taxe_interet_debiteur_1 = taxe_int_1
        arrete.taxe_interet_debiteur_2 = taxe_int_2

        arrete.commission_mvt = com_mvt
        arrete.commission_dec = com_plus_dec

        arrete.taux_commission_mvt = taxe_com_mvt
        arrete.taux_commission_dec = taxe_com_plus_dec

        arrete.frais_fixe = frais_fixe
        arrete.type_account = "Courant" if frais_fixe == 5000 else "Epargne"

        arrete.tva = tva
        arrete.taux_tva = taux_tva

        arrete.net_debit = net_deb
        arrete.solde_agios = solde_val

        arrete.date_deb_arrete = new_dates[0]
        arrete.date_fin_arrete = new_dates[1]
        arrete.date_deb_autorisation = new_dates[2]
        arrete.date_fin_autorisation = new_dates[3]

        try:
            arrete.save()
        except Exception as e:
            print(e)


# Processing functions
def range_file(data_excel):
    # print(data_excel.head())

    res_filter_date = data_excel.copy()

    res_filter_date['index'] = res_filter_date.index
    res_filter_date = res_filter_date.sort_values(by=['date_valeur', 'index'])
    res_filter_date = res_filter_date.drop(columns='index')

    return res_filter_date


# Computation function
def computation_first_table(datas, account):

    # Initialization
    cols = ['CPTABLE', 'VALEUR', 'LIBELLES', 'DEBIT_MVTS', 'CREDIT_MVTS', 'SOLDES', 'SOLDE_JOUR', 'jrs', 'DEBITS_NBR',
            'CREDIT_NBR', 'SOLDES_NBR', 'MVTS_13', 'MVTS_14']
    res_data = {col: [] for col in cols}

    # Initialization

    # Computation part

    # First part
    res_filter_date = datas.copy()

    res_filter_date['index'] = res_filter_date.index
    res_filter_date = res_filter_date.sort_values(by=['date_valeur', 'index'])
    res_filter_date = res_filter_date.drop(columns='index')
    temp_datas = res_filter_date.copy()
    date_valeur = temp_datas['date_valeur'].tolist()

    sold = account['solde_initial']
    j = 1

    date_initiale = date_valeur[0].replace(day=1) - timedelta(days=1)
    res_data['VALEUR'].append(date_initiale.strftime('%d/%m/%Y'))
    res_data['CPTABLE'].append(0)
    res_data['LIBELLES'].append("SOLDE INITIAL")
    res_data['DEBIT_MVTS'].append(sold)
    res_data['CREDIT_MVTS'].append(0)
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

    # Check if account has a discover
    date_debut_auto = pd.to_datetime(account['period'].split('-')[0])
    date_fin_auto = pd.to_datetime(account['period'].split('-')[1])

    if date_debut_auto <= date_initiale <= date_fin_auto:
        mvt_13 = soldes_nbr * jrs if soldes_nbr <= account['montant'] else account['montant'] * jrs
        mvt_14 = debit_nombre - mvt_13

        res_data['MVTS_13'].append(mvt_13)
        res_data['MVTS_14'].append(mvt_14)
    else:
        res_data['MVTS_13'].append(0)
        res_data['MVTS_14'].append(0)

    j = 1
    l = len(date_valeur)
    # Loop and compute values
    for i in range(len(date_valeur)):

        # 1 et 2
        date_cpt = temp_datas.iloc[i]['date_comptable']
        date_val = date_valeur[i]

        res_data['CPTABLE'].append(date_cpt.strftime('%d/%m/%Y'))
        res_data['VALEUR'].append(date_val.strftime('%d/%m/%Y'))

        # 3
        res_data['LIBELLES'].append(temp_datas.iloc[i]['libelle_operation'])

        # 4 & 5
        debit_mvt = 0
        credit_mvt = 0
        montant = temp_datas.iloc[i]['montant']

        if temp_datas.iloc[i].sens == "D":
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
        if date_debut_auto <= date_initiale <= date_fin_auto:
            mvt_13 = soldes_nbr * jrs if soldes_nbr <= account['montant'] else account['montant']  * jrs
            mvt_14 = debit_nombre - mvt_13

            res_data['MVTS_13'].append(mvt_13)
            res_data['MVTS_14'].append(mvt_14)
        else:
            res_data['MVTS_13'].append(0)
            res_data['MVTS_14'].append(0)

    return res_data


def computation_second_table(res_data, account):

    # Get taux_interets_debiteurs
    taux_int_1 = account["taxe_interet_debiteur_1"] / 100
    taux_int_2 = account["taxe_interet_debiteur_2"] / 100
    taux_com_mvts = account["taux_commission_mvt"] / 100
    taux_com_dec = account["taux_commission_dec"] / 100
    tva = account["taux_tva"] / 100

    cols_calcul = ['INT_DEBITEURS_1', 'INT_DEBITEURS_2', 'COM_DE_MVTS', 'COM_DE_DVERT', 'FRAIS_FIXES', 'TVA', 'TOTAL']
    calcul = {col: [] for col in cols_calcul}

    # # 14
    res = (sum(res_data['MVTS_13']) * taux_int_1) / 360
    calcul['INT_DEBITEURS_1'].append(ceil(res))

    # 15
    res = (sum(res_data['MVTS_14']) * taux_int_2) / 360
    calcul['INT_DEBITEURS_2'].append(ceil(res))

    # 16
    seuil = 2000 if account["type_account"] == 'Epargne' else 5000

    int_sum = sum(res_data['DEBIT_MVTS'][1:]) * taux_com_mvts
    # max_val = max(res_data['DEBIT_MVTS'])
    res = int_sum if int_sum < seuil else seuil
    calcul['COM_DE_MVTS'].append(ceil(res))

    # 17
    total_plus_fort = min(res_data['SOLDE_JOUR'])
    res = 0 if total_plus_fort >= 0 else -total_plus_fort * taux_com_dec
    calcul['COM_DE_DVERT'].append(ceil(res))

    # 18
    calcul['FRAIS_FIXES'].append(seuil)

    inter = [calcul[l] for l in list(calcul.keys())[:-1]]
    val = sum(list(map(sum, zip(*inter)))[1]) * tva

    calcul['TVA'].append(ceil(val))

    inter = [calcul[l] for l in list(calcul.keys())[:-1]]
    val = list(map(sum, zip(*inter)))[0]

    calcul['TOTAL'].append(val)
    calcul['TOTAL'].append(" ")

    calcul['INT_DEBITEURS_1'].append(taux_int_1)
    calcul['INT_DEBITEURS_2'].append(taux_int_2)
    calcul['COM_DE_MVTS'].append(taux_com_mvts)
    calcul['COM_DE_DVERT'].append(taux_com_dec)
    calcul['FRAIS_FIXES'].append("")
    calcul['TVA'].append(tva)

    return calcul

# def whole_process(data_filter):
#     result_data = computation_first_table(data_filter)
#     compute = computation_first_table(result_data)
#
#     return result_data, compute
