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
    solde_initial = options['solde_initial']

    # Filtering part
    data_filtering = Historique.objects.filter(num_compte__in=accounts, date_comptable__lte=date_fin,
                                               date_comptable__gte=date_deb, date_valeur__lte=date_fin,
                                               date_valeur__gte=date_deb
                                               ).exclude(code_operation__in=operations).values()

    if len(data_filtering) == 0:
        return Response(500)

    # print(data_filtering)

    # Get filter datas by arretes

    dataframes = []

    for account in accounts:

        datas = list(Arretes.objects.filter(num_compte__in=accounts).values())

        datas_acc = list(Compte.objects.filter(num_compte__in=accounts).values())
        account_type = datas_acc[0]['type_account']

        # datas_accounts = {x['num_compte']:  x['type_account'] for x in datas_acc}

        data_filter_arrete = {x['num_compte']: [x['date_deb_autorisation'], x['date_fin_autorisation'], x['montant']]
                              for x in datas}

        df = pd.DataFrame(data_filtering)

        filter_datas = range_file(df)

        first = computation_first_table(filter_datas, solde_initial, account, data_filter_arrete)
        second = computation_second_table(pd.DataFrame(first), options, account_type)

        new_first = [dict(zip(first, t)) for t in zip(*first.values())]

        for k in list(second.keys()):
            res = {}
            for key in list(first.keys())[:-3]:
                res[key] = " "

            res['SOLDES_NBR'] = k
            res["MVTS_13"] = second[k][1]
            res["MVTS_14"] = second[k][0]
            new_first.append(res)
        # new_second = [dict(zip(second, t)) for t in zip(*second.values())]

        # print(new_first)

        dataframes.append({'first': new_first, 'account': account})

    # print(dataframes)

    return Response({
        'data': dataframes
    })


@api_view(['GET'])
def get_infos(request):

    # Get all  infos base on history
    comptes = pd.DataFrame(list(Compte.objects.all().values()))
    delta = pd.DataFrame(list(Delta.objects.all().values()))
    result = delta.merge(comptes, on="num_compte", how="inner")
    result.date_deb_autorisation = result.date_deb_autorisation.dt.strftime('%d/%m/%Y')
    result.date_fin_autorisation = result.date_fin_autorisation.dt.strftime('%d/%m/%Y')
    result['period'] = result[['date_deb_autorisation', 'date_fin_autorisation']].agg(" - ".join, axis=1)

    return Response(result.T.to_dict().values())


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
    # Compte.objects.all().delete()

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
        if hist.num_compte not in list(accounts.keys()):

            # type_account = 'E'
            #
            # if 'courant' in unidecode(hist.intitule_compte.lower()) or hist.code_operation == 100:
            #     type_account = 'C'
            accounts[hist.num_compte] = []

            accounts[hist.num_compte].append(hist.intitule_compte)

            # accounts[hist.num_compte].append(type_account)
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
            compte.save()

# load datas txt file
def load_data_txt(data_txt):
    # code_agence , account_number, amount, dates = None, None, None, None
    code_agence, account_number, amount, frais_fixe, com_plus_dec, com_mvt, int_1, int_2, taxe_int_1, taxe_int_2, taxe_com_plus_dec, taxe_com_mvt, taux_tva, tva, net_deb, solde_val, dates = [None] * 17

    auto_part = 30
    stri = data_txt.tail(auto_part).values.tolist()
    string_datas = " ".join(stri)

    reg_numb = "( )*(-)?([0-9\.,]+)(\d)+( )*[(TVA)(%)]*"
    regex_dict = {
        'code': '\d{4} -',
        'account': 'XAF-\d{11}-\d{2}',
        'dates' : '(\d\d)[-/](\d\d)[-/](\d\d(?:\d\d)?)',
        'amount' : '([0-9]+\.)+(\d{3}) XAF',
        'taxe_frais': 'TAXE/FRAIS{} ( )* TVA '.format(reg_numb),
        'taxe_com_mvt': 'TAXE/COMMISSION DE MOUVEMENT{}'.format(reg_numb),
        'com_mvt': 'COMMISSION DE MOUVEMENT({})+'.format(reg_numb),
        'com_dec': ' COMMISSION/PLUS FORT DECOUVERT({})+'.format(reg_numb),
        'int_debit':  ' INTERETS DEBITEURS({})+'.format(reg_numb),
        'frais_fixe': 'FRAIS FIXES{}'.format(reg_numb),
        'net_deb': 'NET A DEBITER{}'.format(reg_numb),
        'solde_val': 'SOLDE EN VALEUR APRES AGIOS{}'.format(reg_numb),
        'tva': '(TAXE/INTERETS DEBITEURS|TAXE/COMM. PLUS FORT DECOUVERT|TAXE/COMMISSION DE MOUVEMENT|TAXE/FRAIS)({})+( )*'.format(reg_numb)
    }

    datas = string_datas

    def get_value(colname, position, sep=" "):
        """
        :param: column name, position
        :return: corresponded value
        """
        value = re.search(regex_dict[colname], datas).group(0).split(sep)[position]
        return value

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
        tva = ceil((int_1 + int_2 + com_mvt + com_plus_dec + frais_fixe) * (taux_tva /100))

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
def computation_first_table(datas, solde_initial, account, filter_compte):
    # Initialization
    cols = ['CPTABLE', 'VALEUR', 'LIBELLES', 'DEBIT_MVTS', 'CREDIT_MVTS', 'SOLDES', 'SOLDE_JOUR', 'jrs', 'DEBITS_NBR',
            'CREDIT_NBR', 'SOLDES_NBR', 'MVTS_13', 'MVTS_14']
    res_data = {col: [] for col in cols}

    # Initialization

    # Computation part

    # First part
    res_filter_date = datas[datas['num_compte'] == account]

    res_filter_date['index'] = res_filter_date.index
    res_filter_date = res_filter_date.sort_values(by=['date_valeur', 'index'])
    res_filter_date = res_filter_date.drop(columns='index')
    temp_datas = res_filter_date.copy()
    date_valeur = temp_datas['date_valeur'].tolist()

    sold = solde_initial
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
    if account in list(filter_compte.keys()):
        if filter_compte[account][0] <= date_initiale <= filter_compte[account][1]:
            mvt_13 = soldes_nbr * jrs if soldes_nbr <= filter_compte[account][2] else filter_compte[account][2] * jrs
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
        if account in list(filter_compte.keys()):
            if filter_compte[account][0] <= date_initiale <= filter_compte[account][1]:
                mvt_13 = soldes_nbr * jrs if soldes_nbr <= filter_compte[account][2] else filter_compte[account][
                                                                                              2] * jrs
                mvt_14 = debit_nombre - mvt_13

                res_data['MVTS_13'].append(mvt_13)
                res_data['MVTS_14'].append(mvt_14)
        else:
            res_data['MVTS_13'].append(0)
            res_data['MVTS_14'].append(0)

    return res_data


def computation_second_table(res_data, options, account_type):
    # taux_interets_debiteurs
    taux_int_1 = options['taux_int_1'] / 100
    taux_int_2 = options['taux_int_2'] / 100
    taux_com_mvts = options['taux_com'] / 100
    taux_com_dec = options['fort_dec'] / 100
    tva = options['tva'] / 100

    cols_calcul = ['INT_DEBITEURS_1', 'INT_DEBITEURS_2', 'COM_DE_MVTS', 'COM_DE_DVERT', 'FRAIS_FIXES', 'TVA', 'TOTAL']
    calcul = {col: [] for col in cols_calcul}

    # # 14
    res = (sum(res_data['MVTS_13']) * taux_int_1) / 360
    calcul['INT_DEBITEURS_1'].append(res)

    # 15
    res = (sum(res_data['MVTS_14']) * taux_int_2) / 360
    calcul['INT_DEBITEURS_2'].append(res)

    # 16
    seuil = 2000 if account_type == 'E' else 5000

    int_sum = sum(res_data['DEBIT_MVTS'][1:]) * taux_com_mvts
    # max_val = max(res_data['DEBIT_MVTS'])
    res = int_sum if int_sum < seuil else seuil
    calcul['COM_DE_MVTS'].append(int_sum)

    # 17
    total_plus_fort = min(res_data['SOLDE_JOUR'])
    res = 0 if total_plus_fort >= 0 else -total_plus_fort * taux_com_dec
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
