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
from io import StringIO
from math import ceil
from json import load
from rest_framework.permissions import IsAuthenticated

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
LEN_INTERET_DEBITEURS  = 3


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

    response_computation = []

    # First get the last current historic

    current_user = request.user

    try:
        accounts = request.data['accounts']

        dataframes = []

        for account in accounts:

            data_filtering = Historic.objects.filter(num_compte=account['num_compte']).values()

            if len(data_filtering) == 0:
                return Response(500)

            df = pd.DataFrame(data_filtering)

            # sort data by valeur date
            filter_datas = range_file(df)

            first = computation_first_table(filter_datas, account)

            second = computation_second_table(pd.DataFrame(first), account)

            # Adding ecar
            ecar = []
            col_datas = ['interet_debiteur_1', 'interet_debiteur_2', 'commission_mvt', 'commission_dec', 'frais_fixe',
                         'tva']

            ecar.append(second['INT_DEBITEURS_1'][0] - account['interet_debiteur_1'])
            second['INT_DEBITEURS_1'].extend([account['interet_debiteur_1'], ecar[-1]])

            ecar.append(second['INT_DEBITEURS_2'][0] - account['interet_debiteur_2'])
            second['INT_DEBITEURS_2'].extend([account['interet_debiteur_2'], ecar[-1]])

            ecar.append(second['COM_DE_MVTS'][0] - account['commission_mvt'])
            second['COM_DE_MVTS'].extend([account['commission_mvt'], ecar[-1]])

            ecar.append(second['COM_DE_DVERT'][0] - account['commission_dec'])
            second['COM_DE_DVERT'].extend([account['commission_dec'], ecar[-1]])

            ecar.append(second['FRAIS_FIXES'][0] - account['frais_fixe'])
            second['FRAIS_FIXES'].extend([account['frais_fixe'], ecar[-1]])

            ecar.append(second['TVA'][0] - account['tva'])
            second['TVA'].extend([account['tva'], ecar])

            second['TOTAL'].extend([sum([account[col] for col in col_datas]), sum(ecar)])

            print(second)
            new_first = [dict(zip(first, t)) for t in zip(*first.values())]

            for k in list(second.keys()):
                res = {}
                for key in list(first.keys())[:-5]:
                    res[key] = " "

                res['SOLDES_NBR'] = k
                res["MVTS_13"] = second[k][1]
                res["MVTS_14"] = second[k][0]
                res["MVTS_14"] = second[k][2]
                res["MVTS_14"] = second[k][3]
                new_first.append(res)
            # new_second = [dict(zip(second, t)) for t in zip(*second.values())]            #
            dataframes.append({'first': new_first, 'account': account})
            # print(dataframes)
    except Exception as e:
        print(e)
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
        historic = pd.DataFrame(save_history['historic'])
        accounts = pd.DataFrame(save_history['accounts'])
        accounts = accounts[accounts.type_compte == type_account]
        accounts = list(pd.DataFrame(accounts).T.to_dict().values())
        operations = pd.DataFrame(save_history['operations'])
    else:
        return Response(500)

    delta = list(Echelle.objects.filter(user=request.user).T.to_dict().values())

    # loop through all unique accounts
    new_infos_account = []
    if type_account == "Epargne":

        for info_account in accounts:
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

                # 1- Interets

                echelle_deb, echelle_cred = account_echelle['interets_debiteurs'], account_echelle['interets_crediteurs']

                # Intermediate fonction for interest
                def get_interets_epargne(interets):

                    taux_init = 0
                    int_inf = 0
                    int_sup = 0

                    for ind, item in enumerate(interets):
                        if ind == 0:
                            taux_init = item[1]

                        val_interet = item[0]

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

            # Final step: Update the dictionnary
            info_account.update(autorisations)
            info_account.update(
                {'interet_inf': interet_inf[1], 'taux_interet_inf': interet_inf[0], 'interet_sup': interet_sup[1],
                 'taux_interet_sup': interet_sup[0], 'fraix_fixe': frais_fixe, 'tva': tva[1], 'taux_tva': tva[0],
                 'ircm': ircm[1], 'taux_ircm': ircm[0]})

            new_infos_account.append(info_account)

    elif type_account == "Courant":

        for info_account in accounts:
            interets = [{'taux': 0, 'val': 0} for i in range(LEN_INTERET_DEBITEURS)]
            autorisations = {}
            com_mvt = {'taux': TAUX_COM_MVT, 'val': INITIAL_VALUE}
            com_dec = {'taux': TAUX_DEC, 'val': INITIAL_VALUE}
            tva = {'taux': TAUX_TVA, 'val': INITIAL_VALUE}
            frais_fixe = 5000

            try:
                account_echelle = next(item for item in delta if item['num_compte'] == info_account['account'])
            except Exception as e:
                account_echelle = None

            if account_echelle is not None:

                # interet computing
                echelle_deb = account_echelle['interets_debiteurs']

                if echelle_deb is not None:
                    keys = list(echelle_deb.keys())

                    for i in range(len(keys)):
                        if i == 2:
                            break
                        interets[i].update(echelle_deb[keys[i]])

                # commissions
                if account_echelle["comission_mouvement"] is not None:
                    com_mvt.update(account_echelle["comission_mouvement"])

                if account_echelle["comission_decouvert"] is not None:
                    com_dec.update(account_echelle["comission_decouvert"])

                # tva
                if account_echelle['tva'] is not None:
                    tva[0].update(account_echelle['tva'])

                # frais fixes
                if account_echelle['frais_fixe'] is not None:
                    frais_fixe = account_echelle['frais_fixe']

                if account_echelle['autorisations'] is not None:
                    autorisations.update(account_echelle['autorisations'])


            # Update dict
            info_account.update({"interet_"+ str(i) : a['val'] for i,a in enumerate(interets)})
            info_account.update({"taux_interet_" + str(i): a['taux'] for i,a in enumerate(interets)})
            info_account.update(autorisations)
            info_account.update(
                {'fraix_fixe': frais_fixe, 'tva': tva['val'], 'taux_tva': tva['taux'], 'com_mvt' : com_mvt['val'], 'taux_com_mvt' : com_mvt['taux'],
                 'com_dec' : com_dec['val'], 'taux_com_dec' : com_dec['taux']})
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

        for file in files:

            current_user = request.user

            if file:
                if pathlib.Path(str(file)).suffix in [".xls", ".xlsx"]:

                    print(file)

                    cols_str = ['Code Agence', 'Référence lettrage', 'chapitre', 'N° compte', 'Code Opération']
                    cols_dates = ['Date Comptable', 'Date de Valeur']
                    all_cols = cols_str + cols_dates
                    try:
                        data_excel = pd.read_excel(file, skiprows=2, dtype={val: str for val in cols_str},
                                                   parse_dates=cols_dates, dayfirst=True)
                    except Exception as e:
                        return Response(500)

                    data_excel = data_excel[all_cols]

                    if data_excel.isnull().sum().sum() != 0:
                        return Response(500)
                    # data_excel.drop(columns=['Unnamed: 0'], inplace=True)

                    load_data_excel(data_excel.copy(), current_user)

                else:
                    pass
                    data_excel = pd.read_csv(file, sep='\n', header=None, squeeze=True)
                    load_data_txt(data_excel.copy(), current_user)

        return Response(204)


# Load datas excel file
def load_data_excel(data_excel, current_user):
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

    historic_part = data_excel.to_dict().values()
    formatted_historic = {"historic": historic_part, "accounts": accounts, "operations": operations}

    new_hist.historic = formatted_historic
    new_hist.user = current_user

    try:
        new_hist.save()
    except Exception as e:
        print(e)


# load datas txt file
def load_data_txt(datas_txt, current_user):
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
        'taxe_com_mvt': 'TAXE/COMMISSION DE MOUVEMENT{}'.format(reg_numb),
        'com_mvt': 'COMMISSION DE MOUVEMENT({})+'.format(reg_numb),
        'com_dec': 'COMMISSION/PLUS FORT DECOUVERT({})+'.format(reg_numb),
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

    code_agence, account_number, date_deb_arrete, date_fin_arrete, frais_fixe = [None] * 5

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
            new_date = datetime(res[0], res[1], res[2])
            new_dates.append(new_date)

        date_deb_arrete = new_dates[0]
        date_fin_arrete = new_dates[1]

        frais_fixe = int(re.search(regex_dict['frais_fixe'], datas).group().split()[-1].replace(".", ""))

    except Exception as e:
        print(e)

    # Autorisations

    autorisations = {}
    if len(new_dates) > 2:
        try:
            montants = [int(match.group().replace("XAF", "").replace(".", "")) for match in re.finditer(regex_dict['amount'], datas)]
            autorisations = {}
            j = 0
            for i in range(0, len(new_dates[2:]), 2):
                autorisations.update({ 'montant_' + str(j+1): montants[j], 'debut_autorisation_' + str(j+1): new_dates[i+2],
                                       'fin_autorisation_' + str(j+1): new_dates[i+3]})
                j += 1
        except Exception as e:
            print(e)

    # Interets DEBITEURS
    try:
        interets_debiteurs = {}
        all_int_debiteurs = [match.group() for match in re.finditer(regex_dict['int_credit'], datas)]

        for i, interet in enumerate(all_int_debiteurs):
            interets_debiteurs[i] = []
            val_int = get_interet(interet)
            taxe_int = get_interet(interet, pos_char=-2, sep=",")
            interets_debiteurs[i].extend([val_int, taxe_int])

    except Exception as e:
        print(e)

    # Interets CREDITEURS
    try:
        interets_crediteurs = {}
        all_int_crediteurs = [match.group() for match in re.finditer(regex_dict['int_debit'], datas)]

        for i, interet in enumerate(all_int_crediteurs):
            interets_crediteurs[i] = []
            val_int = get_interet(interet)
            taxe_int = get_interet(interet, pos_char=-2, sep=",")
            interets_crediteurs[i].extend([val_int, taxe_int])
    except Exception as e:
        print(e)

    # IRCM
    try:
        ircm = {}
        all_ircm = re.search(regex_dict['ircm'],
                             string_datas.translate(str.maketrans({val: ' ' for val in ['\n', '!', '-']}))).group(
            0).strip().split()
        ircm['val'] = int(all_ircm[-1])
        ircm['taux'] = float(all_ircm[-2])
    except Exception as e:
        print(e)

    # Commission mouvement
    try:
        commission_mouvement = {}
        res_mvt = [re.search(regex_dict['com_mvt'], datas).group()]
        taxe_com_mvt = get_interet(res_mvt, pos_char=-2, sep=",")
        com_mvt = get_interet(res_mvt)

        commission_mouvement['val'] = com_mvt
        commission_mouvement['taux'] = taxe_com_mvt
    except Exception as e:
        print(e)

    # Commission découvert
    try:
        commission_decouvert = {}
        res_dec = [re.search(regex_dict['com_dec'], datas).group()]
        taxe_com_dec = get_interet(res_dec, pos_char=-2, sep=",")
        com_dec = get_interet(res_dec)

        commission_decouvert['val'] = com_dec
        commission_decouvert['taux'] = taxe_com_dec
    except Exception as e:
        print(e)

    # TVA
    try:
        tva = {}
        all_tva = [match.group() for match in re.finditer(regex_dict['tva'], datas)]
        taux_tva = get_interet(all_tva, pos_char=-3, sep=",")

        taxes_tva = [get_interet(string_tva) for string_tva in all_tva]
        val_tva = ceil(sum(taxes_tva) * (taux_tva / 100))

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
        new_ech.comission_mouvement = commission_mouvement
        new_ech.commission_decouvert = commission_decouvert
        new_ech.tva = tva
        try:
            new_ech.save()
        except Exception as e:
            return Response(500)


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
            mvt_13 = soldes_nbr * jrs if soldes_nbr <= account['montant'] else account['montant'] * jrs
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

    inter = [calcul[l] for l in list(calcul.keys())[:-2]]
    val = list(map(sum, zip(*inter)))[0] * tva

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


def whole_process(data_filter):
    result_data = computation_first_table(data_filter)
    compute = computation_first_table(result_data)

    return result_data, compute
