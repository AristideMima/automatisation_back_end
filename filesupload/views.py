from django.shortcuts import render
from rest_framework import views
from rest_framework.parsers import BaseParser, MultiPartParser
from rest_framework.response import Response
import pandas as pd
import pathlib
from datetime import date, datetime
from pyexcel_xlsx import get_data
from .models import *
from django.utils.timezone import utc, now
import re
from unidecode import unidecode
from rest_framework.decorators import api_view
from .models import Historique

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


@api_view(['POST'])
def make_calcul(request):
    accounts = request.data['accounts']
    operations = request.data['operations']
    options = request.data['options']
    date_deb = options['date_deb']
    date_fin = options['date_fin']

    # Filtering part
    data_filtering = Historique.objects.filter(num_compte__in=accounts, date_comptable__lte=date_fin,
                                               date_comptable__gte=date_deb, date_valeur__lte=date_fin,
                                               date_valeur__gte=date_deb
                                               ).exclude(code_operation__in=operations).values()


    df = pd.DataFrame(data_filtering)

    print(df.head())

    return Response(206)


class FileUpload(views.APIView):
    """
        Class based file upload
    """
    parser_classes = [MultiPartParser]

    # file upload function
    def put(self, request, format=None):

        print("received request")

        file = request.data['file']

        if file:
            print(file)
            if pathlib.Path(str(file)).suffix in [".xls", ".xlsx"]:

                print(file)

                cols_str = ['Code Agence', 'Référence lettrage', 'chapitre', 'N° compte']
                cols_dates = ['Date Comptable', 'Date de Valeur']
                data_excel = pd.read_excel(request.FILES.get('file'), skiprows=2, dtype={val: str for val in cols_str},
                                           parse_dates=cols_dates, dayfirst=True)

                data_excel.drop(columns=['Unnamed: 0'], inplace=True)

                # get filter datas
                # filter_data = filter_file(data_excel.copy(), ['00143451101'])
                #
                # computation_first = computation_first_table(filter_data.copy())
                #
                # computation_second = computation_second_table(computation_first)
                #
                # # print(computation_second)
                #
                # return Response({
                #     'table': computation_first,
                #     'computation': computation_second
                # })
                load_data_excel(data_excel.copy())

            else:
                pass
                data_excel = pd.read_csv(request.FILES.get('file'), sep='\n', header=None, squeeze=True)
                print(data_excel.head())
                load_data_txt(data_excel.copy())

            return Response("Fichier {} uploadé avec succès".format(file))

        return Response(204)


# Load datas excel file
def load_data_excel(data_excel):
    accounts = {}
    operations = set()

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

        operations.add(hist.code_operation)

        if hist.num_compte not in accounts.keys():

            type_account = 'E'

            if 'courant' in unidecode(hist.intitule_compte.lower()) or hist.code_operation == 100:
                type_account = 'C'
            accounts[hist.num_compte] = []
            accounts[hist.num_compte].append(hist.intitule_compte)
            accounts[hist.num_compte].append(type_account)
        try:
            hist.save()

        except Exception as e:
            print(e)

    # Save operations
    if len(operations) != 0:
        for op in operations:
            operation = Operation()
            operation.code_operation = op

            try:
                operation.save()
            except Exception as e:
                print(e)

    # Save accounts
    if len(list(accounts.keys())) != 0:

        for account in list(accounts.keys()):
            compte = Compte()
            compte.num_compte = account
            compte.intitule_compte = accounts[account][0]
            compte.type_account = accounts[account][1]
            compte.save()


# load datas txt file
def load_data_txt(data_txt):
    auto_part = 30
    stri = data_txt.tail(auto_part).values.tolist()
    string_datas = " ".join(stri)

    reg_numb = "( )*(-)?([0-9]+\.)+(\d{3})"
    regex_dict = {
        'code': '\d{4} -',
        'account': 'XAF-\d{11}-\d{2}',
        'dates': '(\d\d)[-/](\d\d)[-/](\d\d(?:\d\d)?)',
        'amount': '([0-9]+\.)+(\d{3}) XAF',
        'taxe_frais': 'TAXE/FRAIS{}'.format(reg_numb),
        'taxe_com_mvt': 'TAXE/COMMISSION DE MOUVEMENT{}'.format(reg_numb),
        'com_mvt': 'COMMISSION DE MOUVEMENT{}'.format(reg_numb),
        'com_dec': 'COMMISSION/PLUS FORT DECOUVERT{}'.format(reg_numb),
        'int_debit': 'INTERETS DEBITEURS{}'.format(reg_numb),
        'fraix_fixe': 'FRAIS FIXES{}'.format(reg_numb),
        'net_deb': 'NET A DEBITER{}'.format(reg_numb),
        'solde_val': 'SOLDE EN VALEUR APRES AGIOS{}'.format(reg_numb),
    }

    datas = string_datas

    def get_value(colname, position, sep=" "):
        """
        :param: column name, position
        :return: corresponded value
        """
        value = re.search(regex_dict[colname], datas).group(0).split(sep)[position]
        return value

    code_agence = get_value('code', 0)
    account_number = get_value('account', 1, "-")
    amount = int(get_value('amount', 0).replace(".", ""))
    dates = re.findall(regex_dict['dates'], datas)

    arrete = Arretes()

    # dates conversion
    new_dates = []
    for single_date in dates:
        res = [int(num) for num in single_date[::-1]]
        new_date = datetime(res[0], res[1], res[2])
        new_dates.append(new_date)

    arrete.code_agence = code_agence
    arrete.num_compte = account_number
    arrete.montant = amount
    arrete.date_deb_arrete = new_dates[0]
    arrete.date_fin_arrete = new_dates[1]
    arrete.date_deb_autorisation = new_dates[2]
    arrete.date_fin_autorisation = new_dates[3]

    try:
        arrete.save()
    except Exception as e:
        print(e)


# Processing functions
def filter_file(data_excel, list_account):
    # print(data_excel.head())

    # account_list = ['00143451101']
    account_vals = data_excel[data_excel['N° compte'].isin(list_account)]
    # res_filter_date = account_vals.copy()

    period = [datetime(2020, 11, 10), datetime(2021, 11, 25)]

    res_filter_date = account_vals[
        ((account_vals['Date Comptable'] > period[0]) & (account_vals['Date de Valeur'] > period[0])) &
        ((account_vals['Date Comptable'] < period[1]) & (account_vals['Date de Valeur'] < period[1]))]

    res_filter_date['index'] = res_filter_date.index
    res_filter_date = res_filter_date.sort_values(by=['Date de Valeur', 'index'])
    res_filter_date = res_filter_date.drop(columns='index')
    print(res_filter_date.info())

    return res_filter_date


# Computation function
def computation_first_table(datas):
    # Initialization
    cols = ['CPTABLE', 'VALEUR', 'LIBELLES', 'DEBIT_MVTS', 'CREDIT_MVTS', 'SOLDES', 'SOLDE_JOUR', 'jrs', 'DEBITS_NBR',
            'CREDIT_NBR', 'SOLDES_NBR', 'MVTS_13', 'MVTS_14']
    res_data = {col: [] for col in cols}

    solde = 0

    # Computation part

    # First part
    temp_datas = datas.copy()

    date_valeur = temp_datas['Date de Valeur'].tolist()
    sold = 0
    j = 1

    # Loop and compute values
    for i in range(len(date_valeur)):

        # 1 et 2
        date_cpt = temp_datas.iloc[i]['Date Comptable']
        date_val = date_valeur[i]

        #     temp = temp_datas[(temp_datas['Date Comptable'] == date_cpt) & (temp_datas['Date de Valeur'] == date_val)]

        res_data['CPTABLE'].append(date_cpt.strftime('%Y-%m-%d'))
        res_data['VALEUR'].append(date_val.strftime('%Y-%m-%d'))

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

        temp_datas.iloc[0]['Montant']
        res_data['DEBIT_MVTS'].append(debit_mvt)
        res_data['CREDIT_MVTS'].append(credit_mvt)

        # 6
        sold += + res_data['CREDIT_MVTS'][-1] - res_data['DEBIT_MVTS'][-1]
        res_data['SOLDES'].append(sold)

        # 8
        nbj = abs((date_val - date_valeur[j - 1]).days)
        j = i + 1
        res_data['jrs'].append(nbj)

        # 7
        res_data['SOLDE_JOUR'].append(sold if sold != 0 else 0)

        # 9 & 10 & 11
        # pour comptes d’épargnes et les comptes en intérêts créditeurs
        debit_nombre = -sold * nbj if sold < 0 else 0
        credit_nombre = sold * nbj if sold > 0 else 0

        res_data['DEBITS_NBR'].append(debit_nombre)
        res_data['CREDIT_NBR'].append(credit_nombre)

        soldes_nombre = -sold if sold < 0 else 0

        res_data['SOLDES_NBR'].append(soldes_nombre)

        # 12 Découvert non échu
        dec_amount = 145
        mvt_13 = sold * nbj if sold <= dec_amount else dec_amount * nbj
        mvt_14 = debit_nombre - mvt_13

        res_data['MVTS_13'].append(mvt_13)
        res_data['MVTS_14'].append(mvt_14)

    return res_data


def computation_second_table(res_data):
    # taux_interets_debiteurs
    taux_int_1 = 0.135
    taux_int_2 = 0.145
    taux_com_mvts = 0.00025
    taux_com_dec = 0.00025
    tva = 0.1925

    cols_calcul = ['INT_DEBITEURS_1', 'INT_DEBITEURS_2', 'COM_DE_MVTS', 'COM_DE_DVERT', 'FRAIS_FIXES', 'TVA', 'TOTAL']
    calcul = {col: [] for col in cols_calcul}

    # 14
    res = sum(res_data['MVTS_13']) * taux_int_1
    calcul['INT_DEBITEURS_1'].append(res)

    # 15
    res = (sum(res_data['MVTS_13']) * taux_int_2) / 360
    calcul['INT_DEBITEURS_2'].append(res)

    # 16
    int_sum = sum(res_data['DEBIT_MVTS']) * taux_com_mvts
    max_val = max(res_data['DEBIT_MVTS'])
    res = max_val if int_sum <= max_val else int_sum
    calcul['COM_DE_MVTS'].append(res)

    # 17
    total_plus_fort = min(res_data['SOLDE_JOUR'])
    res = 0 if total_plus_fort >= 0 else total_plus_fort * taux_com_dec
    calcul['COM_DE_DVERT'].append(res)

    # 18
    frais_fixe = 5000
    calcul['FRAIS_FIXES'].append(frais_fixe)

    inter = [calcul[l] for l in list(calcul.keys())[:-2]]
    val = list(map(sum, zip(*inter)))[0] * tva

    calcul['TVA'].append(val)

    inter = [calcul[l] for l in list(calcul.keys())[:-1]]
    val = list(map(sum, zip(*inter)))[0]

    calcul['TOTAL'].append(val)

    return calcul


def whole_process(data_filter):
    result_data = computation_first_table(data_filter)
    compute = computation_first_table(result_data)

    return result_data, compute
