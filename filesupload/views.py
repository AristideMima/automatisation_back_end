from __future__ import absolute_import
from rest_framework import views
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
import pandas as pd
from datetime import timedelta, date
from .models import *
from rest_framework.decorators import api_view
from math import ceil
from rest_framework.permissions import IsAuthenticated
from django.http import JsonResponse
from tqdm import tqdm
import os
from datetime import datetime
from celery import shared_task
from celery_progress.backend import ProgressRecorder
from celery import Celery
# import holidays
from .constants import *
import psutil
from automatisation_arrete_backend.constants import engine

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
TAUX_INT_DEB1 = 15.5
TAUX_INT_DEB2 = 6.5
TAUX_INT_DEB3 = 0
LEN_INTERET_DEBITEURS = 3
PATH_HISTORIQUE = "static/historiques/"
PATH_AUTORISATION = "static/autorisations/"
PATH_COMPTE = "static/comptes/"
PATH_SOLDE = "static/soldes/"
PATH_JOURNAUX = "static/journaux/"
PATH_OPERATIONS = "static/operations/"

# Celery app definition
app = Celery('automatisation_arrete_backend.filesupload', backend='rpc://', broker='pyamqp://guest@localhost//')


@api_view(['POST'])
def compute_files(request):
    try:
        files_historic = request.FILES.getlist('Historic[]')
        file_ladder = request.FILES.getlist('Ladder[]')
        file_sold = request.FILES.getlist('Sold')
    except:
        return Response({'message': 'FIchiers requis absents'}, status=500)


    # read all historics
    histos = []
    for file in files_historic:
        try:
            historic = pd.read_excel(file)
            historic = historic[colhistoric]
            historic[comptable] = pd.to_datetime(historic[comptable], errors="ignore").dt.date
            historic[valeur] = pd.to_datetime(historic[valeur], errors="ignore").dt.date
            historic[code] = historic[code].astype(int)
            historic[montant] = historic[montant].astype(int)
            historic[cle] = historic[cle].astype(str)
            historic[compte] = historic[compte].apply(lambda x: str(x).zfill(11))
            historic[agence] = historic[agence].apply(lambda x: str(x).zfill(5))
            historic[compte] = historic[agence] + "-" + historic[compte] + "-" + historic[cle]
            histos.append(historic)
        except:
            return Response({'message': 'Problème de lecture des historiques '}, status=500)

    histos = pd.concat(histos)
    histos = histos.drop_duplicates()

    # Deal with file sold
    try:
        data_sold = pd.read_excel(file_sold[0], usecols=colsold)
        data_sold[sold] = data_sold[sold].astype(int)
        data_sold[compte] = data_sold[compte].apply(lambda x: str(x).zfill(11))
        data_sold[agence] = data_sold[agence].apply(lambda x: str(x).zfill(5))
        data_sold[cle] = data_sold[cle].astype(str)
        data_sold[compte] = data_sold[agence] + "-" + data_sold[compte] + "-" + data_sold[cle]
        data_sold.drop_duplicates(subset=[compte], keep="first")
    except Exception as e:
        return Response({'message': 'Problème de lecture des fichiers de solde '}, status=500)



    all_results = []
    # Read all accounts files
    for account_file in file_ladder:
        full_account = str(account_file).split(".")[0]
        account_number = ""
        code_agence = ""

        res_data = {"account": full_account, "results_dict": [], "compute_dict": {}}

        data_str = None
        try:
            data_file_txt = pd.read_csv(account_file, sep='\n', header=None, squeeze=True)
            string_list = data_file_txt.tail(auto_part).values.tolist()
            data_str = " ".join(string_list)
        except:
            continue

        try:
            account_number = get_value('account', 1, data_str, "-", True)
            code_agence = get_value('code', 0, data_str)
        except Exception as e:
            print(e)
            pass
        account_number = account_number.replace("XAF", code_agence)

        if len(account_number.split("-")) != 3:
            continue
        else:
            if account_number.split("-")[0] == '':
                continue

        fees = 2_000
        dates = None
        net_deb = 0
        val_sold = 0


        init_sold = 0
        tva = {'val': 0, 'tax': 0}
        ircm = {'val': 0, 'tax': 0}



        # get init sold
        # Get initial sold for the current account
        acc_sold = data_sold[data_sold[compte] == account_number]

        if len(acc_sold) != 0:
            init_sold = int(acc_sold.iloc[0][sold])


        try:
            # 1- Fees
            fees = int(re.search(regex_dict_val['frais_fixe'], data_str).group().split()[-1].replace(".", ""))
        except:
            pass

            # 2- Dates
        try:
            dates = re.findall(regex_dict_val['dates'], data_str)
        except:
            pass

        if dates is None:
            all_results.append(res_data)
            continue

        # get all dates
        new_dates = []
        for single_date in dates:
            res = [int(num) for num in single_date[::-1]]
            new_date = date(res[0], res[1], res[2])
            new_dates.append(new_date)

        date_start = pd.to_datetime(new_dates[0])
        date_end = pd.to_datetime(new_dates[1])


        try:
            # Filter historic for that account
            filter_data = historic[historic[compte] == account_number]

            # Filter for period inside ladder
            filter_data = filter_data[((date_start.date() <= filter_data[valeur]) & (filter_data[valeur] <= date_end.date())) & (
                    (date_start.date() <= filter_data[comptable]) & (filter_data[comptable] <= date_end.date()))]

            # Range historic
            filter_data = range_file(filter_data)

            if(len(filter_data) == 0):
                continue
        except:
            all_results.append(res_data)
            continue

        # 4- Ircm
        try:
            all_ircm = re.search(regex_dict_val['ircm'], data_str.translate(str.maketrans({val: ' ' for val in ['\n', '!', '-']}))).group(0).strip().split()
            ircm['val'] = int(all_ircm[-1].replace('.', ''))
            ircm['tax'] = float(all_ircm[-2].replace(',', '.'))
        except Exception as e:
            pass

        # 5 - Tva
        try:
            all_tva = [match.group() for match in re.finditer(regex_dict_val['tva'], data_str)]
            # print(all_tva)
            tax_tva = get_interet(all_tva, pos_char=-3, sep=",")
            all_val_int = [int(val.split()[-1].replace(".", "")) for val in all_tva]
            val_tva = ceil(sum(all_val_int) + fees + ircm['val']) * (tax_tva / 100)
            tva = {'val': val_tva, 'tax': tax_tva}
        except:
            pass
            # pass


        try:
            net_deb = int(re.search(regex_dict_val['net_deb'], data_str).group().split()[-1].replace(".", ""))
        except:
            pass

        try:
            val_sold = int(re.search(regex_dict_val['solde_val'], data_str).group().split()[-1].replace(".", ""))
        except:
            pass

        if str(account_number[1][-4:-1]) in table_saving:
            # Compute saving numbers


            # Initial parameters
            tva = {'val': 0, 'tax': 0}
            int_tax = []

            # 3- Interests
            try:
                int_credit_all = [match.group() for match in re.finditer(regex_dict_val['int_credit'], data_str)]

                for ind, val in enumerate(int_credit_all):
                    val = get_interet(int_credit_all, ind)
                    tax = get_interet(int_credit_all, pos_string=ind, pos_char=-2, sep=",")
                    int_tax.append((val, tax))
            except:
                pass

            parameters_dict = {
                'fees': fees,
                'ircm': ircm,
                'tva': tva,
                'int_tax': int_tax,
                'date_start': date_start,
                'date_end': date_end,
                'net_deb': net_deb,
                'val_sold': val_sold,
                'init_sold': init_sold,
                'account_number': full_account
            }

            # make final computation
            res_data = compute_unique_saving(filter_data, parameters_dict)
        else:
            # Compute current number

            com_mvt = {'val': 0, 'tax': 0}
            com_dec = {'val': 0, 'tax': 0}
            int_tax = []
            autos = []

            # 3- Interests
            try:
                int_debit_all = [match.group() for match in re.finditer(regex_dict_val['int_debit'], data_str)]

                for ind, val in enumerate(int_debit_all):
                    val = get_interet(int_debit_all, ind)
                    tax = get_interet(int_debit_all, pos_string=ind, pos_char=-2, sep=",")
                    int_tax.append((int(val), float(tax)))
            except:
                pass

            # Com dec:
            try:
                res_plus_dec = [re.search(regex_dict_val['com_dec'], data_str).group()]
                tax_com_plus_dec = get_interet(res_plus_dec, pos_char=-2, sep=",")
                com_plus_dec = get_interet(res_plus_dec)
                com_dec = {'val': int(com_plus_dec), 'tax': float(tax_com_plus_dec)}
            except:
                pass


            # Com Mvt:
            try:
                res_mvt = [re.search(regex_dict_val['com_mvt'], data_str).group()]
                tax_com_mvt = get_interet(res_mvt, pos_char=-2, sep=",")
                com_plus_mvt = get_interet(res_mvt)
                com_mvt = {'val': int(com_plus_mvt), 'tax': float(tax_com_mvt)}
            except:
                pass


            # get autorisations
            if len(new_dates) > 2:
                try:
                    autos_find = re.findall(regex_dict_val['amount'], data_str)
                    autos_int = [int(amount.split()[0].replace(".", "")) for amount in autos_find]
                    final_len = len(new_dates) - len(autos_int)
                    autos = [(autos_int[i // final_len], new_dates[i], new_dates[i + 1]) for i in
                             range(2, len(new_dates), 2)]
                except Exception as e:
                    pass


            parameters_dict = {
                'fees': fees,
                'tva': tva,
                'int_tax': int_tax,
                'date_start': date_start,
                'date_end': date_end,
                'com_mvt': com_mvt,
                'com_dec': com_dec,
                'auto': autos,
                'val_sold': val_sold,
                'init_sold': init_sold,
                'account_number': full_account
            }

            res_data = compute_unique_saving(filter_data, parameters_dict, saving=False)

            # print(parameters_dict)
            # return Response({'message': 'Just a random response to hurt you - account'}, status=500)

        all_results.append(res_data)

    return Response({'data': all_results})


# Compute unique saving function:
def compute_unique_saving(historic, parameters_dict, saving=True):
    # Initial parameters computation
    value_int = 50_000_000
    init_sold = parameters_dict['init_sold']

    # Compute the first line
    init_values = {
        comptable: [''],
        valeur: [parameters_dict['date_start']],
        libelle: ["SOLDE INITIAL"],
        debit: [init_sold] if init_sold < 0 else [0],
        credit: [init_sold] if init_sold >= 0 else [0],
    }

    last_values = {
        comptable: [''],
        valeur: [parameters_dict['date_end']],
        libelle: [""],
        debit: [0],
        credit: [0],
    }

    # Extract only useful values
    short_historic = historic[[comptable, valeur, libelle, montant, sens]]
    short_historic[debit] = short_historic.apply(lambda x: x[montant] if x[sens] == 'D' else 0, axis=1)
    short_historic[credit] = short_historic.apply(lambda x: x[montant] if x[sens] == 'C' else 0, axis=1)
    short_historic.drop(columns=[montant, sens], inplace=True)
    short_historic = pd.concat([pd.DataFrame(init_values), short_historic, pd.DataFrame(last_values)])
    short_historic[normal_sold] = short_historic[credit] - short_historic[debit]
    short_historic[normal_sold] = short_historic[normal_sold].cumsum()
    short_historic[valeur] = pd.to_datetime(short_historic[valeur])
    short_historic[day] = short_historic[valeur].diff().shift(-1)
    short_historic[day] = short_historic[day].apply(lambda x: x.days)
    short_historic[day] = short_historic[day].fillna(0).astype(int)

    # Other computation
    short_historic[sold_day] = short_historic[[day, normal_sold]].apply(lambda x: x[normal_sold] if x[day] != 0 else 0, axis=1)
    short_historic[debit_number] = short_historic[[day, normal_sold]].apply(lambda x: -1 * x[day] * x[normal_sold] if x[normal_sold] < 0 else 0, axis=1)
    short_historic[credit_number] = short_historic[[day, normal_sold]].apply(lambda x: x[day] * x[normal_sold] if x[normal_sold] > 0 else 0, axis=1)


    if saving:
        short_historic[sold_number] = short_historic[[day, normal_sold]].apply(lambda x: x[normal_sold] if x[normal_sold] > 0 and x[day] > 0 else 0, axis=1)
        short_historic[mvt_first_saving] = short_historic[[sold_number, day]].apply(
            lambda x: x[day] * x[sold_number] if x[sold_number] <= value_int else value_int * x[day], axis=1)
        short_historic[mvt_second_saving] = short_historic[credit_number] - short_historic[mvt_first_saving]
    else:
        short_historic[sold_number] = short_historic[[day, normal_sold]].apply(lambda x: x[normal_sold] if x[normal_sold] < 0 and x[day] > 0 else 0, axis=1)
        short_historic[mvt_first_saving] = short_historic[[sold_number, day, valeur]].apply(compute_dec, autos=parameters_dict['auto'], axis=1)
        short_historic[mvt_second_saving] = short_historic[debit_number] - short_historic[mvt_first_saving]


    int_tax = parameters_dict['int_tax']

    # Compute final values and ecarts
    if saving:
        int_sup = ceil((sum(short_historic[mvt_second_saving]) * float(int_tax[0][0])) / 360)
        ircm = ceil(int_sup * float(parameters_dict['ircm']['tax']))

        global_compute = {
            "int_inf": 0,
            "int_sup": 0,
            "icrm": 0,
            "fees": 0,
            "tva": 0
        }
        if len(parameters_dict['int_tax']) == 2:
            global_compute = {
                "int_inf": ceil((sum(short_historic[mvt_first_saving]) * float(int_tax[0][0]))/ 360),
                "int_sup": int_sup,
                "icrm": ircm,
                "fees": int(parameters_dict['fees']),
                "tva": int(parameters_dict['fees']) * float(parameters_dict['tva']['tax'])
            }
        elif len(parameters_dict['int_tax']) == 1:
            global_compute = {
                "int_inf": (sum(short_historic[mvt_first_saving]) * float(int_tax[0][0])) / 360,
                "int_sup": 0,
                "icrm": ircm,
                "fees": int(parameters_dict['fees']),
                "tva": int(parameters_dict['fees']) * float(parameters_dict['tva']['tax'])
            }
    else:
        com_mvt = ceil(sum(short_historic[debit]) * parameters_dict['com_mvt']['tax'])
        com_dec = ceil(min(short_historic[sold_day]) * parameters_dict['com_dec']['tax'])
        global_compute = {
            "fees": int(parameters_dict['fees']),
            "com_mvt": 2_000 if com_mvt < 2_000 else com_mvt,
            "com_dec": -1 * ceil(com_dec) if com_dec < 0 else 0,
        }

        for index, val in enumerate(int_tax):
            first_val = sum(short_historic[mvt_first_saving])
            second_val = sum(short_historic[mvt_second_saving])
            tax = val[1]

            if tax == 15.5 and second_val != 0:
                global_compute["int_" + str(index)] = ceil((second_val * tax)/360)
            else:
                global_compute["int_" + str(index)] = ceil((first_val * tax)/360)

        prev_val_tva = sum([global_compute[key] for key in list(global_compute.keys())])

        global_compute['tva'] = int(prev_val_tva * float(parameters_dict['tva']['tax']))

        global_compute['total'] = sum([global_compute[key] for key in list(global_compute.keys())])

    return {"account": parameters_dict['account_number'], "results_dict": list(short_historic.T.to_dict().values()),
            "compute_dict": global_compute}


def compute_dec(row, autos):
    val = row[valeur]
    sold_value = row[sold_number]
    day_value = row[day]

    all_amount = sum([auto_val[0] for auto_val in autos if auto_val[1] <= val.date() <= auto_val[2]])

    final_amount = day_value * sold_value if sold_value <= all_amount else day_value * all_amount

    return final_amount


# Get some statistics
@api_view(['GET'])
def get_statistics(request):
    # Files and user count
    total_files = File.objects.count()
    total_files_courant = File.objects.filter(file_type="courant").count()
    total_files_epargne = File.objects.filter(file_type="epargne").count()
    hdd = psutil.disk_usage('/')

    stats_epargne = computation_statistics('epargne', globalstat=True)
    stats_courant = computation_statistics('courant')

    # total_user = User.objects.count()
    res_data = {
        "epargne": stats_epargne,
        "courant": stats_courant,
        "total": total_files_courant + total_files_epargne,
        "totalUnique": total_files,
        "total_courant": total_files_courant,
        "total_epargne": total_files_epargne,
        "size_total": int(hdd.total / (2 ** 30)),
        "used": int(hdd.used / (2 ** 30)),
        "total_sim": stats_epargne['total_sim']
    }

    return Response(res_data)


def computation_statistics(type, globalstat=False):
    statistics = pd.DataFrame(list(Statisticepargne.objects.all().values()))

    total_sim = 0
    if type == "courant":
        statistics = pd.DataFrame(list(Statisticourant.objects.all().values()))
    total = 0

    if globalstat:

        if type == "courant":
            statclass = Statisticepargne
        else:
            statclass = Statisticourant

        try:
            globdata = pd.concat([statistics, pd.DataFrame(list(statclass.objects.all().values()))])
            total_sim = len(globdata)
            # ecart = abs(globdata['ecart'].sum())
            sim = globdata['simulation_total'].sum()
            journ = globdata['journal_total'].sum()

            total = (sim - journ) / journ
            # globdatastat = (globdata.groupby('agence')[["ecart"]].agg(['sum']).astype(int)).reset_index()
            #
            # globdatastat.columns = ['_'.join(col) if col[1] != '' else col[0] for col in globdatastat.columns]
            # globdatastat = globdatastat.rename(columns={"agence": "id", "ecart_sum": "value"})
            # globdatastat['label'] = globdatastat.index

        except:
            pass
            # globdatastat = []
        # print(globdatastat.columns)
    try:
        statistics['period'] = (pd.to_datetime(statistics['date_fin'])).dt.strftime("%m-%Y")

        statagence = (
            statistics.groupby('agence')[['simulation_total', 'journal_total', "ecart"]].agg(['sum', 'count'])).astype(
            int).reset_index()
        statagence.columns = ['_'.join(col) if col[1] != '' else col[0] for col in statagence.columns]
        statagence.loc["Total"] = statagence.sum(numeric_only=True)
        statagence = statagence.fillna({"agence": "Totaux"})
        statagence['type'] = type

        statagenceperiod = (
            statistics.groupby(['period', 'agence'])[['simulation_total', 'journal_total', "ecart"]].agg(
                ['sum', 'count'])).astype(int).reset_index()
        statagenceperiod.columns = ['_'.join(col) if col[1] != '' else col[0] for col in statagenceperiod.columns]
        statagenceperiod.loc["Total"] = statagenceperiod.sum(numeric_only=True)
        statagenceperiod = statagenceperiod.fillna({"agence": "Totaux", "period": ""})
        statagenceperiod['type'] = type

        # Compute debit interest (First drop unecessaries values)
        statistics = statistics.drop(columns=['created_at', 'type', 'num_account', 'user_id', "ecart", "agence"])
        count = len(statistics)
        if type == "epargne":
            statistics = statistics.drop(columns=['valeur_credit'])

            columns = col_int_val_epargne
            statistics["int_cred_sim"] = statistics["simulation_int_inf"] + statistics["simulation_int_sup"] + \
                                         statistics["simulation_ircm"]
            statistics["int_cred_journ"] = statistics["journal_int_inf"] + statistics["journal_int_sup"] + statistics[
                "journal_ircm"]

            statistics["variation_cred"] = statistics["int_cred_sim"] - statistics["int_cred_journ"]
            statistics["variation_frais"] = statistics["simulation_frais"] - statistics["journal_frais"]
            statistics["variation_tva"] = statistics["simulation_tva"] - statistics["journal_tva"]
            statistics["variation_total"] = statistics["simulation_total"] - statistics["journal_total"]

            statistics = statistics.drop(
                columns=['simulation_int_inf', 'simulation_int_sup', 'simulation_ircm', 'journal_int_inf',
                         'journal_int_sup', 'journal_ircm', 'date_deb', 'date_fin'])

            statsintper = (statistics.groupby(['period']).agg(['sum', 'count'])).astype(int).reset_index()
            statsintper.loc["Total"] = statsintper.sum(numeric_only=True)
            statsintper = statsintper.fillna('Total')
            statsintper['type'] = type

            colsimsum = [
                statistics["int_cred_sim"].sum(),
                statistics["simulation_frais"].sum(),
                statistics["simulation_tva"].sum()
            ]

            coljournsum = [
                statistics["int_cred_journ"].sum(),
                statistics["journal_frais"].sum(),
                statistics["journal_tva"].sum()
            ]

            le = len(col_int_val_epargne)
        else:
            columns = col_int_val
            le = len(columns)

            statistics["int_deb_sim"] = statistics["simulation_int_1"] + statistics["simulation_int_2"] + statistics[
                "simulation_int_3"]
            statistics["int_deb_journ"] = statistics["journal_int_1"] + statistics["journal_int_2"] + statistics[
                "journal_int_3"]

            statistics["variation_int_deb"] = statistics["int_deb_sim"] - statistics["int_deb_journ"]
            statistics["variation_com_dec"] = statistics["simulation_com_dec"] - statistics["journal_com_dec"]
            statistics["variation_com_mvt"] = statistics["simulation_com_mvt"] - statistics["journal_com_mvt"]
            statistics["variation_frais"] = statistics["simulation_frais"] - statistics["journal_frais"]
            statistics["variation_tva"] = statistics["simulation_tva"] - statistics["journal_tva"]
            statistics["variation_total"] = statistics["simulation_total"] - statistics["journal_total"]

            statistics = statistics.drop(
                columns=['simulation_int_1', 'simulation_int_2', 'simulation_int_3', 'journal_int_1', 'journal_int_2',
                         'journal_int_3', 'date_deb', 'date_fin'])
            # col_final = ['int_deb_sim', 'int_deb_journ', 'simulation_com_dec', 'simulation_com_mvt','journal_com_dec','journal_com_mvt','journal_tva','simulation_tva','simulation_frais','journal_frais','variation_int_deb','variation_com_dec','variation_com_mvt','variation_frais','variation_tva']

            statsintper = (statistics.groupby(['period']).agg(['sum', 'count'])).astype(int).reset_index()
            statsintper.loc["Total"] = statsintper.sum(numeric_only=True)
            statsintper = statsintper.fillna('Total')
            statsintper['type'] = type

            colsimsum = [
                statistics["int_deb_sim"].sum(),
                statistics["simulation_com_dec"].sum(),
                statistics["simulation_com_mvt"].sum(),
                statistics["simulation_frais"].sum(),
                statistics["simulation_tva"].sum()
            ]

            coljournsum = [
                statistics["int_deb_journ"].sum(),
                statistics["journal_com_dec"].sum(),
                statistics["journal_com_mvt"].sum(),
                statistics["journal_frais"].sum(),
                statistics["journal_tva"].sum()
            ]
        var_sum = [x1 - x2 for (x1, x2) in zip(colsimsum, coljournsum)]
        var_sum.append(sum(var_sum))
        colsimsum.append(sum(colsimsum))
        coljournsum.append(sum(coljournsum))
        # var_count = [x1 - x2 for (x1, x2) in zip(colsimsum, coljournsum)]
        new_data = {
            "element": columns,
            "simulation_count": [count] * le,
            "simulation_sum": colsimsum,
            "journal_count": [count] * le,
            "journal_sum": coljournsum,
            "variation_count": [count] * le,
            "variation_sum": var_sum,
        }
        # if type == "courant":
        #     print(new_data)

        statsint = pd.DataFrame(new_data)
        statsint['type'] = type

        # print(statistics.columns)
        statsintperiod = (statistics.groupby('period').agg(['sum', 'count'])).astype(int).reset_index()
        statsintperiod.columns = ['_'.join(col) if col[1] != '' else col[0] for col in statsintperiod.columns]
        statsintperiod.loc["Total"] = statsintperiod.sum(numeric_only=True)
        statsintperiod = statsintperiod.fillna({"period": "Totaux"})
        statsintperiod['type'] = type

        all_values = {"total_sim": total_sim, "global": total, "agence": list(statagence.T.to_dict().values()),
                      "agenceper": list(statagenceperiod.T.to_dict().values()),
                      "int": list(statsint.T.to_dict().values()),
                      "intperiod": list(statsintperiod.T.to_dict().values())}
    except Exception as e:
        print(e)
        all_values = {"total_sim": total_sim, "global": total, "agence": [], "agenceper": [],
                      "int": [], "intperiod": []}

    return all_values


global regex_dict

regex_dict = {
    'excel': '[(*.xls)(xlsx]'
}

CODES_PATH = "static/libelle_codes.json"


@api_view(['POST'])
def delete_file(request):
    id = request.data['id']
    type = request.data['type']
    user = request.user

    # Delete file inside disk and delete inside database
    file = File.objects.get(id=id)
    file_path = file.file_folder

    # dict_paths = {"autorisation": PATH_AUTORISATION, "solde": PATH_SOLDE, "historique": PATH_HISTORIQUE,
    #               "operation": PATH_OPERATIONS, "compte": PATH_COMPTE, "journal": PATH_JOURNAUX}

    path_histo = "static/" + type + "/" + file_path + "historic.xlsx"
    path_solde = "static/" + type + "/" + file_path + "soldes.xlsx"
    path_journal = "static/" + type + "/" + file_path + "journal.xlsx"
    path_autorisation = "static/" + type + "/" + file_path + "autorisation.xlsx"

    # complete_path = dict_paths[type] + file_path

    if os.path.exists(path_histo):

        try:

            os.remove(path_histo)
            os.remove(path_solde)
            os.remove(path_journal)

            # Remove also accounts and operations if historique type
            if type == "courant":
                os.remove(path_autorisation)

            file.delete()
            ActiveFileUser.objects.filter(file_id=id).delete()
        except Exception as e:
            print(e)
            default_response = JsonResponse({"message": "Erreur lors de la suppression"}, status=500)
            return default_response
    else:
        default_response = JsonResponse({"message": "Ce fichier n'existe pas"}, status=500)
        return Response(default_response)

    file = retrieve_files(type, user)

    return Response(file)


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
        # files.sort_values(by='created_at', ascending=False)
        files['active_file'] = files['index'].apply(lambda x: False if x != len(files) else True)

        active_files = pd.DataFrame(list(ActiveFileUser.objects.filter(type=type, user=user).all().values()))

        if len(active_files) != 0:
            active_id = active_files['file_id'].iloc[0]
            files['active_file'] = files['id'].apply(lambda x: True if x == active_id else False)
        res = files.T.to_dict().values()
    except Exception as e:
        print(e)
        pass

    return res


@api_view(['POST'])
def make_calcul(request):
    # Get data passed by request
    # We will compute all data separately

    # Load parameters
    try:
        accounts = pd.DataFrame(request.data['accounts'])
        options = request.data['options']
        # operations = pd.DataFrame(request.data['operations'])
        type_account = request.data['type_account']
        user = request.user

        if type_account == "courant":
            accounts['debut_autorisation'] = pd.to_datetime(accounts['debut_autorisation'])
            accounts['fin_autorisation'] = pd.to_datetime(accounts['fin_autorisation'])
        date_deb = pd.to_datetime(options["date_deb"])
        date_fin = pd.to_datetime(options["date_fin"])
        type_arrete = request.data['type_arrete']
        ordre = request.data['ordre']
        int_epargne = request.data['int_epargne']
        file_path = request.data['file_path']
    except Exception as e:
        print(e)
        return JsonResponse({'message': 'Erreur de paramètres'})

    # Load latest history
    try:
        # path_history = PATH_HISTORIQUE + last_history.file_path
        path_history = "static/" + type_account + "/" + file_path + "historic.xlsx"
        history = pd.DataFrame(pd.read_excel(path_history))
        history[compte] = history[compte].astype(str).str.zfill(11)
        history[comptable] = pd.to_datetime(history[comptable])
        history[valeur] = pd.to_datetime(history[valeur])

        path_journal = "static/" + type_account + "/" + file_path + "journal.xlsx"
        journal = pd.DataFrame(pd.read_excel(path_journal))

    except FileNotFoundError as e:
        print(e)
        return default_response_upload
    # # Load Journal
    # try:
    #
    #     try:
    #         req = ActiveFileUser.objects.get(user_id=user, type=type_account)
    #         last_journal = File.objects.get(id=req.file.id).last()
    #     except Exception as e:
    #         print(e)
    #         last_journal = File.objects.get(active_file=True, file_type="journal")
    #     path_journal = "static/" + type_account + "/" + last_history.file_path + "journal.xlsx"
    #     # path_journal = PATH_JOURNAUX + last_journal.file_path
    #     journal = pd.DataFrame(pd.read_excel(path_journal, compression="gzip"))
    #     journal[compte] = journal[compte].astype(str).str.zfill(11)
    #
    # except FileNotFoundError as e:
    #     print(e)

    # If we are not doing regularisation
    # if not type_arrete:
    #     accounts = accounts[['num_compte']]
    #     accounts.rename(columns={'num_compte': 'N° Compte'}, inplace=True)
    #
    #     data_sold, data_auto = [None] * 2
    #     try:
    #         try:
    #             req = ActiveFileUser.objects.get(user_id=user, type="solde")
    #             last_solde = File.objects.get(id=req.file.id)
    #         except Exception as e:
    #             print(e)
    #             last_solde = File.objects.get(active_file=True, file_type="solde")
    #         path_solde = PATH_SOLDE + last_solde.file_path
    #         data_sold = pd.read_csv(path_solde)
    #         data_sold['N° Compte'] = data_sold['N° Compte'].astype(str).str.zfill(11)
    #         data_sold['Date Solde'] = pd.to_datetime(data_sold['Date Solde'])
    #
    #         data_sold = data_sold[(date_deb > data_sold['Date Solde'])]
    #         data_sold.sort_values(by="Date Solde", ascending=False, inplace=True)
    #     except Exception as e:

    #         print(e)
    #
    #     if data_sold is not None:
    #
    #         accounts = accounts.merge(data_sold[['N° Compte', 'Solde']], on='N° Compte', how="left")
    #         accounts = accounts.groupby(['N° Compte']).first().reset_index()
    #         accounts.rename(columns={"Solde": "solde_initial"}, inplace=True)
    #         accounts['solde_initial'].fillna(0, inplace=True)
    #
    #     else:
    #         accounts['solde_initial'] = 0
    #
    #     if type_account == "Courant":
    #         # Add last sold
    #         # Add autorisations
    #         try:
    #             try:
    #                 req = ActiveFileUser.objects.get(user_id=user, type="autorisation")
    #                 last_auto = File.objects.get(id=req.file)
    #             except Exception as e:
    #                 print(e)
    #                 last_auto = File.objects.get(active_file=True, file_type="autorisation")
    #             path_auto = PATH_AUTORISATION + last_auto.file_path
    #             data_auto = pd.read_csv(path_auto, compression="gzip")
    #             data_auto['Date Mise en Place'] = pd.to_datetime(data_auto['Date Mise en Place'])
    #             data_auto['Date de fin'] = pd.to_datetime(data_auto['Date de fin'])
    #             data_auto['N° Compte'] = data_auto['N° Compte'].astype(str).str.zfill(11)
    #             data_auto = data_auto[
    #                 ((date_deb >= data_auto['Date Mise en Place']) & (data_auto['Date de fin'] >= date_fin))]
    #             data_auto.sort_values(by="Montant", ascending=False, inplace=True)
    #         except Exception as e:
    #             print(e)
    #
    #         if data_auto is not None:
    #             accounts = accounts.merge(data_auto[['Date de fin', 'Date Mise en Place', 'Montant', 'N° Compte']],
    #                                       on='N° Compte', how="left")
    #             accounts = accounts.groupby(['N° Compte']).first().reset_index()
    #             accounts.rename(columns={'Date de fin': 'fin_autorisation', 'Montant': 'montant',
    #                                      'Date Mise en Place': 'debut_autorisation'}, inplace=True)
    #             accounts['montant'].fillna(0, inplace=True)
    #             accounts['fin_autorisation'].fillna("", inplace=True)
    #             accounts['debut_autorisation'].fillna("", inplace=True)
    #         else:
    #             accounts['montant'] = 0
    #             accounts['debut_autorisation'] = ""
    #             accounts['fin_autorisation'] = ""
    #
    #         accounts.rename(columns={"N° Compte": "num_compte"}, inplace=True)
    #         accounts['debut_autorisation'] = pd.to_datetime(accounts['debut_autorisation'])
    #         accounts['fin_autorisation'] = pd.to_datetime(accounts['fin_autorisation'])

    # try:
    #     accounts.rename(columns={"N° Compte": "num_compte"}, inplace=True)
    # except Exception as e:
    #     print(e)

    # Filter by account & by operations
    unique_accounts = list(accounts[num_account].unique())
    history = history[(history[compte].isin(unique_accounts))]

    # history = history[(history['N° Compte'].isin(unique_accounts) )]

    # libelles_pass = "(INT. CREDITEURS)|(TAXE FRAIS FIXE)|(PRELEVEMENT LIBERATOIRE)|(FRAIS FIXE)"
    # history = history[~history['Libellé Opération'].str.contains(libelles_pass)]
    # compute real sold based on
    # restriced_history = history[(date_deb > history['Date de Valeur'])][['N° Compte', 'Montant', 'Sens']]
    # restriced_history_two = history[(date_fin < history['Date de Valeur'])][['N° Compte', 'Montant', 'Sens']]

    # # Month m-1
    last_month_day = date_deb.replace(day=1) - timedelta(days=1)
    last_month = date_deb.replace(day=1) - timedelta(days=last_month_day.day)
    next_mont = date_fin + timedelta(days=1)
    history = history[((last_month <= history[comptable]) & (history[comptable] <= next_mont))]
    history = history[((date_deb <= history[valeur]) & (history[valeur] <= date_fin)) & (
            (date_deb <= history[comptable]) & (history[comptable] <= date_fin))]

    if len(history) == 0:
        return JsonResponse({"message": "Aucun historique sur cette date pour les comptes choisis"}, status=500)

    if ordre:
        history = range_file(history)

    if type_arrete:
        accounts = accounts.apply(lambda x: update_account(type_account, x, options))

    # Compute stuff
    results = []
    compressed_results = []
    if type_account == "courant":
        for index, account in tqdm(accounts.iterrows(), total=accounts.shape[0]):

            filter_data = history[history[compte] == account[num_account]]
            if len(filter_data) == 0:
                continue

            res_values = [intdeb1, intdeb2, intdeb3, commvt, comdec, frais, tva, net]
            account.update({value: 0 for value in res_values})
            try:
                if not type_arrete:
                    acc_journal = journal[journal[compte] == account[num_account]].iloc[0]
                    account.update({value: acc_journal[value] for value in res_values})
            except Exception:
                pass

            first = computation_first_table(filter_data, account, date_deb, date_fin)

            second, cols = computation_second_table(pd.DataFrame(first), account, options[opt_frais])

            # Add detailled Results
            new_first = [dict(zip(first, t)) for t in zip(*first.values())]

            new_second = []

            # Format values according to normal computation

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
                res = {'SOLDES': key, "SOLDE_JOUR": second[key][0], "jrs": second[key][1],
                       "DEBITS_NBR": int(account[res_values[i]]),
                       "CREDIT_NBR": second[key][1] - int(account[res_values[i]])}
                new_first.append(res)

            data_first = {'first': new_first, 'account': account[num_account], "second": new_second}

            # Add compressed Results
            data_compressed = {"id": index, compte: account[num_account], "Calcul": second['TOTAL'][-1],
                               "Journal": "Valeur absente", "Ecart": 0, "date_deb": options["date_deb"],
                               "date_fin": options["date_fin"]}
            if not type_arrete and user.type == "dcpo":

                try:
                    ecart = (second['TOTAL'][-1]) - account[net]
                    data_compressed = {"id": index, compte: account[num_account], "Calcul": second['TOTAL'][-1],
                                       "Journal": account[net], "Ecart": ecart, "date_deb": options["date_deb"],
                                       "date_fin": options["date_fin"]}

                    try:
                        stats = Statisticourant()
                        stats.user = user
                        stats.type = type_account
                        stats.num_account = account[num_account]
                        stats.simulation_total = account[net]
                        stats.simulation_int_1 = second[cols[0]][-1]
                        stats.simulation_int_2 = second[cols[1]][-1]
                        stats.simulation_int_3 = second[cols[2]][-1]
                        stats.simulation_com_mvt = second[cols[3]][-1]
                        stats.simulation_com_dec = second[cols[4]][-1]
                        stats.simulation_frais = second[cols[5]][-1]
                        stats.simulation_tva = second[cols[6]][-1]
                        stats.journal_total = account[net]
                        stats.journal_int_1 = account[intdeb1]
                        stats.journal_int_2 = account[intdeb2]
                        stats.journal_int_3 = account[intdeb3]
                        stats.journal_com_dec = account[comdec]
                        stats.journal_com_mvt = account[commvt]
                        stats.journal_tva = account[tva]
                        stats.journal_frais = account[frais]
                        stats.ecart = ecart
                        stats.agence = account[num_account].split('-')[0]
                        stats.date_deb = date_deb.date()
                        stats.date_fin = date_fin.date()
                        stats.save()

                    except Exception:
                        pass
                except Exception as e:
                    pass

            results.append(data_first)
            compressed_results.append(data_compressed)
    elif type_account == "epargne":
        for index, account in tqdm(accounts.iterrows(), total=accounts.shape[0]):

            filter_data = history[history[compte] == account[num_account]]
            if len(filter_data) == 0:
                continue

            res_values = [intinf, intsup, ircm, frais, tva, net]
            account.update({value: 0 for value in res_values})

            try:
                if not type_arrete:
                    acc_journal = journal[journal[compte] == account[num_account]].iloc[0]
                    account.update({value: acc_journal[value] for value in res_values})
            except:
                pass

            first = computation_first_table_epargne(filter_data, account, date_deb, date_fin, int_epargne)

            second, cols = computation_second_table_epargne(pd.DataFrame(first), account, int_epargne,
                                                            options[opt_frais])

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
                res = {'SOLDES': key, "SOLDE_JOUR": second[key][0], "jrs": second[key][1],
                       "DEBITS_NBR": int(account[res_values[i]]),
                       "CREDIT_NBR": second[key][1] - int(account[res_values[i]])}
                new_first.append(res)

            data_first = {'first': new_first, 'account': account[num_account], "second": new_second}

            # Add compressed Results

            data_compressed = {"id": index, compte: account[num_account], "Calcul": second['TOTAL'][-1],
                               "Journal": "Valeur absente", "Ecart": 0, "date_deb": options["date_deb"],
                               "date_fin": options["date_fin"]}

            if not type_arrete and user.type == "dcpo":

                try:
                    account_journal_value = account[net]
                    ecart = (second['TOTAL'][-1]) - account_journal_value
                    data_compressed = {"id": index, compte: account[num_account], "Calcul": second['TOTAL'][-1],
                                       "Journal": account_journal_value, "Ecart": ecart,
                                       "date_deb": options["date_deb"], "date_fin": options["date_fin"]}
                    # [int_inf, int_sup, 'IRCM', 'FRAIS_FIXES', 'TVA', 'TOTAL']

                    try:
                        stats = Statisticepargne()
                        stats.user = user
                        stats.type = type_account
                        stats.agence = account[num_account].split('-')[0]
                        stats.num_account = account[num_account]
                        stats.simulation_int_inf = second[cols[0]][-1]
                        stats.simulation_int_sup = second[cols[1]][-1]
                        stats.simulation_ircm = second[cols[2]][-1]
                        stats.simulation_frais = second[cols[3]][-1]
                        stats.simulation_tva = second[cols[4]][-1]
                        stats.simulation_total = second[cols[5]][-1]

                        stats.journal_int_inf = account[intinf]
                        stats.journal_int_sup = account[intsup]
                        stats.journal_ircm = account[ircm]
                        stats.journal_frais = account[frais]
                        stats.journal_tva = account[tva]
                        stats.journal_total = account[net]
                        stats.valeur_credit = int_epargne
                        stats.ecart = ecart
                        stats.date_deb = date_deb.date()
                        stats.date_fin = date_fin.date()
                        stats.save()
                    except Exception as e:
                        print(e)
                except Exception as e:
                    print(e)

            results.append(data_first)
            compressed_results.append(data_compressed)
    if len(results) == 0:
        return JsonResponse({'message': 'Aucun historique sur la période'})
    response = {"all_data": results, "compressed_data": compressed_results}
    return Response(response)


def update_account(type, account, options):
    if type == "courant":
        account[int1_rate] = options[list(options.keys())[0]]
        account[int2_rate] = options[list(options.keys())[1]]
        account[int3_rate] = options[list(options.keys())[2]]
        account[com_rate] = options[list(options.keys())[3]]
        account[dec_rate] = options[list(options.keys())[4]]
    else:
        account[inf_rate] = options[opt_taux_interet_inferieur]
        account[sup_rate] = options[opt_taux_interet_superieur]
        account[ircm_rate] = options[opt_taux_ircm]

    account[tva_rate] = options[opt_taux_tva]

    return account


@api_view(['POST'])
def get_infos(request):
    user = request.user
    type_account = request.data['type_account']

    datas = get_all_infos(user, type_account)

    return Response(datas)


def get_all_infos(user, type_account):
    # Get request information

    default_data = {"accounts": [], "file_path": ""}
    # Read last path

    try:
        try:
            # print(list(ActiveFileUser.objects.all().values()))
            req = ActiveFileUser.objects.get(user=user.id, type=type_account)
            last_history = File.objects.get(id=req.file.id)
        except Exception as e:
            try:
                last_history = File.objects.filter(file_type=type_account).last()
            except Exception as e:
                return default_data
    except FileNotFoundError as e:
        return default_data

    try:

        # Basics data reading
        path_account = "static/" + type_account + "/" + last_history.file_folder + "comptes.xlsx"
        # path_historic = "static/" + type_account + "/" + last_history.file_folder + "historic.xlsx"
        # path_operation = PATH_OPERATIONS + last_history.file_path
        accounts = pd.read_excel(path_account)
        # historic = pd.read_excel(path_historic)
        accounts = accounts[accounts[typecompte] == type_account].copy()
        # accounts[compte] = accounts[compte].astype(str).str.zfill(11)

        # # Get soldes
        # path_solde = "static/" + type_account + "/" + last_history.file_folder + "soldes.xlsx"
        # data_sold = pd.read_excel(path_solde)
        # data_sold[compte] = data_sold[compte].astype(str).str.zfill(11)
        #
        # accounts = accounts.merge(data_sold[[compte, sold]], on=compte, how="left")
        # accounts = accounts.groupby([compte]).first().reset_index()
        # accounts.rename(columns={sold: "solde_initial"}, inplace=True)
        # accounts['solde_initial'].fillna(0, inplace=True)

        # Get journal values
        # path_journal = "static/" + type_account + "/" + last_history.file_folder + "journal.xlsx"
        # journal = pd.read_excel(path_journal)
        # accounts = accounts.merge(journal, on=compte, how="left")
        # accounts = (accounts.groupby([compte]).first().reset_index()).fillna(0)

    except Exception as e:
        return default_data
    try:
        if type_account == "courant":
            # # Add autorisations
            # path_auto = "static/" + type_account + "/" + last_history.file_folder + "autorisation.xlsx"
            # data_auto = pd.read_excel(path_auto)
            # data_auto[compte] = data_auto[compte].astype(str).str.zfill(11)
            #
            # accounts = accounts.merge(data_auto[[datefin, datedeb, montant, compte]], on=compte, how="left")
            # accounts = accounts.groupby([compte]).first().reset_index()
            # accounts.rename(columns={datefin: 'fin_autorisation', datedeb: 'debut_autorisation'}, inplace=True)
            # accounts[montant].fillna(0, inplace=True)
            # accounts['fin_autorisation'].fillna("", inplace=True)
            # accounts['debut_autorisation'].fillna("", inplace=True)

            rates = pd.DataFrame(list(Ratecourant.objects.all().values()))
            accounts.rename(columns={compte: num_account, typecompte: "type_compte"}, inplace=True)

            if len(rates) != 0:
                accounts.rename(columns={compte: num_account, typecompte: "type_compte"}, inplace=True)
                accounts = accounts.merge(rates, on=num_account, how='left')
                accounts = accounts.groupby([compte]).first().reset_index()
                accounts[com_rate].fillna(TAUX_COM_MVT, inplace=True)
                accounts[dec_rate].fillna(TAUX_DEC, inplace=True)
                accounts[tva_rate].fillna(TAUX_TVA, inplace=True)
                accounts[int1_rate].fillna(TAUX_INT_DEB1, inplace=True)
                accounts[int2_rate].fillna(TAUX_INT_DEB2, inplace=True)
                accounts[int3_rate].fillna(TAUX_INT_DEB3, inplace=True)
            else:
                accounts[com_rate] = TAUX_COM_MVT
                accounts[dec_rate] = TAUX_DEC
                accounts[tva_rate] = TAUX_TVA
                accounts[int1_rate] = TAUX_INT_DEB1
                accounts[int2_rate] = TAUX_INT_DEB2
                accounts[int3_rate] = TAUX_INT_DEB3

        else:
            rates = pd.DataFrame(list(Rateepargne.objects.all().values()))
            accounts.rename(columns={compte: num_account, typecompte: "type_compte"}, inplace=True)

            if len(rates) != 0:
                accounts = accounts.merge(rates, on=num_account, how='left')
                accounts = accounts.groupby([compte]).first().reset_index()
                accounts[inf_rate].fillna(TAUX_INT_EPARGNE, inplace=True)
                accounts[sup_rate].fillna(TAUX_INT_EPARGNE, inplace=True)
                accounts[tva_rate].fillna(TAUX_TVA, inplace=True)
                accounts[ircm_rate].fillna(TAUX_IRCM_EPARGNE, inplace=True)
            else:
                accounts[inf_rate] = TAUX_INT_EPARGNE
                accounts[sup_rate] = TAUX_INT_EPARGNE
                accounts[tva_rate] = TAUX_TVA
                accounts[ircm_rate] = TAUX_IRCM_EPARGNE
    except Exception as e:
        print(e)
        return default_data

    # Finish
    # res_accounts = accounts[accounts['Type de Compte'] == type_account].copy()
    res_accounts = accounts.copy()
    res_accounts.rename(columns={montant: "montant"}, inplace=True)
    res_accounts['key'] = res_accounts.index

    res_accounts = list(res_accounts.T.to_dict().values())

    if res_accounts is not None:
        default_data = {"accounts": res_accounts, "file_path": last_history.file_folder}

    return default_data


class FileUpload(views.APIView):
    """
        Class based file upload
    """
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated]

    # file upload function
    def put(self, request, format=None):

        files = request.FILES.getlist('files[]')
        choice = request.data['choice']
        period = request.data['period']
        type = request.data['type']

        # Read files, check if empty,

        if len(files) == 0:
            return Response({"message": "Aucun fichier à charger"}, status=500)

        if type == default_type_loading:

            rates = pd.read_excel(files[0])

            if rates.isnull().sum().sum() != 0:
                return JsonResponse({"message": "Le fichier de taux contient des valeurs nulles "}, status=500)

            try:
                rates[cle] = rates[cle].astype(str)
                rates[compte] = rates[compte].apply(lambda x: str(x).zfill(11))
                rates[agence] = rates[agence].apply(lambda x: str(x).zfill(5))
                rates[compte] = rates[agence] + "-" + rates[compte] + "-" + rates[cle]

                # Get all datas from database
                if choice == default_option_courant:
                    insertrates(rates, colratecourant, Ratecourant, table_courant, rename_cols_courant)
                else:
                    insertrates(rates, colrateepargne, Rateepargne, table_epargne, rename_cols_epargne)

            except Exception as e:
                print(e)
                return JsonResponse(
                    {"message": "Le fichier de taux  {} ne respecte pas le format requis".format(choice)}, status=500)

        else:
            # file = files[0]
            file_path = str(datetime.now()).replace(":", "").replace("/", "").replace(" ", "").replace(".", "").replace(
                "-", "")
            if request.user.type != "dcpo":
                default_response = JsonResponse({"message": " Vous n'êtes pas autorisé à faire cette opération"},
                                                status=500)
                return default_response

            # Match corresponding choices
            try:
                historic = pd.read_excel(files[0])
                soldes = pd.read_excel(files[1])
                journal = pd.read_excel(files[2])

                if choice == "courant":
                    autorisation = pd.read_excel(files[3])

                # Read general files

                try:
                    historic = historic[colhistoric]
                    historic[comptable] = pd.to_datetime(historic[comptable], errors="ignore").dt.date
                    historic[valeur] = pd.to_datetime(historic[valeur], errors="ignore").dt.date
                    historic[code] = historic[code].astype(int)
                    historic[montant] = historic[montant].astype(int)
                    historic[cle] = historic[cle].astype(str)
                    historic[compte] = historic[compte].apply(lambda x: str(x).zfill(11))
                    historic[agence] = historic[agence].apply(lambda x: str(x).zfill(5))
                    historic[compte] = historic[agence] + "-" + historic[compte] + "-" + historic[cle]
                except Exception:
                    return JsonResponse(
                        {"message": "Le fichier historique ne respecte pas le format requis. Voir l'aide"}, status=500)

                comptes = historic[[compte, intitule]]
                comptes.drop_duplicates(subset=[compte])
                comptes[typecompte] = comptes[compte].apply(lambda x: "epargne" if x[-7:-4] == "110" else "courant")

                # Solde
                try:
                    soldes = soldes[colsold]
                    soldes[datesold] = pd.to_datetime(soldes[datesold], errors="ignore").dt.date
                    soldes[compte] = soldes[compte].apply(lambda x: str(x).zfill(11))
                    soldes[agence] = soldes[agence].apply(lambda x: str(x).zfill(5))
                    soldes[sold] = soldes[sold].astype(int)
                    soldes[cle] = soldes[cle].astype(str)
                    soldes[compte] = soldes[agence] + "-" + soldes[compte] + "-" + soldes[cle]

                    comptes = comptes.merge(soldes[[compte, sold]], on=compte, how="left")
                    comptes = comptes.groupby([compte]).first().reset_index()
                    comptes.rename(columns={sold: "solde_initial"}, inplace=True)
                    comptes['solde_initial'].fillna(0, inplace=True)
                except Exception:
                    return JsonResponse(
                        {"message": "Le fichier de solde ne respecte pas le format requis. Voir l'aide"}, status=500)
                path = pathcourant
                if choice == "courant":

                    # Autorisation
                    try:
                        autorisation = autorisation[colautorisation]
                        autorisation[datedeb] = pd.to_datetime(autorisation[datedeb], errors="ignore").dt.date
                        autorisation[datefin] = pd.to_datetime(autorisation[datefin], errors="ignore").dt.date
                        autorisation[montant] = autorisation[montant].astype(int)
                        autorisation[compte] = autorisation[compte].apply(lambda x: str(x).zfill(11))
                        autorisation[cle] = autorisation[cle].astype(str)
                        autorisation[agence] = autorisation[agence].apply(lambda x: str(x).zfill(5))
                        autorisation[compte] = autorisation[agence] + "-" + autorisation[compte] + "-" + autorisation[
                            cle]

                        comptes = comptes.merge(autorisation[[datefin, datedeb, montant, compte]], on=compte,
                                                how="left")
                        comptes = comptes.groupby([compte]).first().reset_index()
                        comptes.rename(columns={datefin: 'fin_autorisation', datedeb: 'debut_autorisation'},
                                       inplace=True)
                        comptes[montant].fillna(0, inplace=True)
                        comptes['fin_autorisation'].fillna("", inplace=True)
                        comptes['debut_autorisation'].fillna("", inplace=True)
                    except Exception:
                        return JsonResponse(
                            {"message": "Le fichier d'autorisation ne respecte pas le format requis. Voir l'aide"},
                            status=500)

                    # Journal
                    try:
                        journal = journal[coljournalcourant]
                        journal[net] = journal[net].astype(int)
                        journal[comdec] = journal[comdec].astype(int)
                        journal[commvt] = journal[commvt].astype(int)
                        journal[frais] = journal[frais].astype(int)
                        journal[tva] = journal[tva].astype(int)
                        journal[intdeb1] = journal[intdeb1].astype(int)
                        journal[intdeb2] = journal[intdeb2].astype(int)
                        journal[intdeb3] = journal[intdeb3].astype(int)
                        journal[cle] = journal[cle].astype(str)
                        journal[compte] = journal[compte].apply(lambda x: str(x).zfill(11))
                        journal[agence] = journal[agence].apply(lambda x: str(x).zfill(5))
                        journal[compte] = journal[agence] + "-" + journal[compte] + "-" + journal[cle]

                        # Get journal values
                    except Exception:
                        return JsonResponse(
                            {"message": "Le fichier de journal Courant ne respecte pas le format requis. Voir l'aide"},
                            status=500)

                else:
                    try:
                        path = pathepargne
                        journal = journal[coljournalepargne]
                        journal[cle] = journal[cle].astype(str)
                        journal[compte] = journal[compte].apply(lambda x: str(x).zfill(11))
                        journal[agence] = journal[agence].apply(lambda x: str(x).zfill(5))
                        journal[compte] = journal[agence] + "-" + journal[compte] + "-" + journal[cle]
                        journal[net] = journal[net].astype(int)
                        journal[cle] = journal[cle].astype(str)
                        journal[frais] = journal[frais].astype(int)
                        journal[tva] = journal[tva].astype(int)
                        journal[ircm] = journal[ircm].astype(int)
                        journal[intinf] = journal[intinf].astype(int)
                        journal[intsup] = journal[intsup].astype(int)

                    except:
                        return JsonResponse(
                            {"message": "Le fichier de journal épargne ne respecte pas le format requis. Voir l'aide"},
                            status=500)

                if historic.isnull().sum().sum() != 0 and soldes.isnull().sum().sum() != 0 and journal.isnull().sum().sum() != 0:
                    return JsonResponse({"message": "Un des fichiers contient des valeurs nulles"}, status=500)

                historic.to_excel(path + file_path + "historic.xlsx", index=False)
                comptes = comptes.merge(journal, on=compte, how="left")
                comptes = (comptes.groupby([compte]).first().reset_index()).fillna(0)
                comptes.to_excel(path + file_path + "comptes.xlsx", index=False)
                soldes.to_excel(path + file_path + "soldes.xlsx", index=False)
                journal.to_excel(path + file_path + "journal.xlsx", index=False)

                if choice == "courant":

                    if autorisation.isnull().sum().sum() != 0:
                        return JsonResponse({"message": "Un des fichiers contient des valeurs nulles"}, status=500)

                    # saved files
                    autorisation.to_excel(path + file_path + "autorisation.xlsx", index=False)

                try:
                    upload = File()
                    upload.user = request.user
                    upload.file_folder = file_path
                    upload.file_type = choice
                    upload.period = period
                    upload.save()
                except Exception as e:
                    print(e)
                    return JsonResponse({
                        "message": "Les fichiers pour cette période et le type {} sont déjà présents en base de données".format(
                            choice)}, status=500)

            except Exception as e:
                print(e)
                return default_response_upload

        return Response(204)


def insertrates(rates, col, model, table, renames):
    rates = rates[col]
    rates = rates.drop_duplicates(subset=[compte])
    num_accounts = pd.unique(rates[compte])

    obj = model.objects.filter(num_account__in=num_accounts)
    obj.delete()

    rates.rename(columns=renames, inplace=True)
    rates.drop(columns=drop_cols, inplace=True)
    try:
        rates.to_sql(table, con=engine, if_exists='append', index=False)
    except Exception as e:
        print(e)


# def clean_net_client(net_client):
#     res = re.sub(r'[a-zA-Z\.,]', '', str(net_client))
#     res = res.replace(".", "")
#     return int(res)
#
#
# def clean_account(account):
#     res = account.split("-")[0]
#
#     res = str(res).zfill(11)
#
#     return res
#
#
# def fill_operation(code_operation):
#     libelle_operation = "No libelle"
#     try:
#         libelle_operation = codes[code_operation]
#     except Exception as e:
#         pass
#
#     return libelle_operation


# Modify last record
def modify_last_record(choice):
    prev = File.objects.get(active_file=True, file_type=choice)
    prev.active_file = False
    prev.save()


def save_file(user, file_path, choice, options):
    try:
        new_file = File()
        new_file.user = user
        new_file.file_folder = file_path
        new_file.file_type = choice
        # new_file.date_inf = options['date_inf']
        # new_file.date_sup = options['date_sup']
        # new_file.longueur = options['len']
        # new_file.active_file = True
        new_file.save()
        return None
    except Exception as e:
        print(e)
        return "oups"


# Processing functions
def range_file(data_excel):
    res_filter_date = data_excel.copy()

    res_filter_date['index'] = res_filter_date.index
    res_filter_date = res_filter_date.sort_values(by=[valeur, 'index'])
    res_filter_date = res_filter_date.drop(columns='index')

    return res_filter_date


# ----- System conform computation -----#

# Computation function for courant
def computation_first_table(datas, account, date_deb, date_fin):
    # Initialization
    cols = ['CPTABLE', 'VALEUR', 'LIBELLES', 'DEBIT_MVTS', 'CREDIT_MVTS', 'SOLDES', 'SOLDE_JOUR', 'jrs', 'DEBITS_NBR',
            'CREDIT_NBR', 'SOLDES_NBR', 'MVTS_13', 'MVTS_14']
    res_data = {col: [] for col in cols}

    # Computation part

    # First part
    res_filter_date = datas.copy()

    montant_account = int(account["montant"])

    # range by date value
    res_filter_date['index'] = res_filter_date.index
    res_filter_date = res_filter_date.sort_values(by=[valeur, 'index'])
    res_filter_date = res_filter_date.drop(columns='index')
    temp_datas = res_filter_date.copy()
    date_valeur = temp_datas[valeur].tolist()

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
    soldes_nombre = -soldes if (soldes < 0 and jrs > 0) else 0
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
    for index, row in temp_datas.iterrows():

        # 1 et 2
        date_cpt = row[comptable]
        date_val = row[valeur]
        # code_operation = row[code_operation]
        # res_data['code_operation'].append(code_operation)

        res_data['CPTABLE'].append(date_cpt.strftime('%d/%m/%Y'))
        res_data['VALEUR'].append(date_val.strftime('%d/%m/%Y'))

        # 3
        res_data['LIBELLES'].append(row[libelle])

        # 4 & 5
        debit_mvt = 0
        credit_mvt = 0
        Montant = row[montant]

        if row[sens] == "D":
            debit_mvt = Montant
        else:
            credit_mvt = Montant

        res_data['DEBIT_MVTS'].append(debit_mvt)
        res_data['CREDIT_MVTS'].append(credit_mvt)

        soldes += res_data['CREDIT_MVTS'][-1] - res_data['DEBIT_MVTS'][-1]
        res_data['SOLDES'].append(soldes)

        if j < l:
            jrs = abs((date_valeur[j] - date_val).days)
        else:
            jrs = abs((date_fin - date_val).days)
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


def computation_second_table(res_data, account, frais):
    # Get taux_interets_debiteurs

    taux_int_1 = float(account[int1_rate]) / 100
    taux_int_2 = float(account[int1_rate]) / 100
    taux_int_3 = float(account[int1_rate]) / 100
    taux_com_mvts = float(account[com_rate]) / 100
    taux_com_dec = float(account[dec_rate]) / 100
    tva = float(account[tva_rate]) / 100
    frais_fixe = frais

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

    # df = pd.DataFrame(res_data)
    # df = df.merge(pd.DataFrame(operations)[['code_operation', 'com_dec', 'com_mvt']], on="code_operation",how="left")

    df_mvt_sum = sum(res_data['DEBIT_MVTS'])
    seuil = 2000

    int_sum = df_mvt_sum * taux_com_mvts

    res = seuil if int_sum < seuil else int_sum
    calcul['COM_DE_MVTS'].append(int(res))

    # 17
    df_dec_min = min(res_data['SOLDE_JOUR'])
    total_plus_fort = df_dec_min
    res = 0 if total_plus_fort >= 0 else -total_plus_fort * taux_com_dec
    calcul['COM_DE_DVERT'].append(int(res))

    # 16
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

    return calcul, cols_calcul


# COMPUTATION FOR EPARGNE

def computation_first_table_epargne(datas, account, date_deb, date_fin, int_epargne):
    # Initialization
    cols = ['CPTABLE', 'VALEUR', 'LIBELLES', 'DEBIT_MVTS', 'CREDIT_MVTS', 'SOLDES', 'SOLDE_JOUR', 'jrs', 'DEBITS_NBR',
            'CREDIT_NBR', 'SOLDES_NBR', 'MVTS_13', 'MVTS_14']
    res_data = {col: [] for col in cols}

    comp_dec_epargne = int_epargne

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

    # libelles_pass = ["INT. CREDITEURS", "TAXE FRAIS FIXE", "PRELEVEMENT LIBERATOIRE", "FRAIS FIXE"]
    for index, row in temp_datas.iterrows():
        #
        # libelle = row[libelle]
        # res = [lib in libelle for lib in libelles_pass]
        # if any(res):
        #     continue

        # 1 et 2
        date_cpt = row[comptable]
        date_val = row[valeur]

        res_data['CPTABLE'].append(date_cpt.strftime('%d/%m/%Y'))
        res_data['VALEUR'].append(date_val.strftime('%d/%m/%Y'))

        # 3
        res_data['LIBELLES'].append(libelle)

        # 4 & 5
        debit_mvt = 0
        credit_mvt = 0
        Montant = row[montant]

        if row[sens] == "D":
            debit_mvt = Montant
        else:
            credit_mvt = Montant

        res_data['DEBIT_MVTS'].append(debit_mvt)
        res_data['CREDIT_MVTS'].append(credit_mvt)

        soldes += res_data['CREDIT_MVTS'][-1] - res_data['DEBIT_MVTS'][-1]
        res_data['SOLDES'].append(soldes)

        if j < l:
            jrs = abs((date_valeur[j] - date_val).days)
        else:
            jrs = abs((date_fin - date_val).days)

        # jrs = abs((date_valeur[j] - date_val).days)
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


def computation_second_table_epargne(res_data, account, int_epargne, frais):
    # Get taux_interets_debiteurs
    taux_int_1 = float(account[inf_rate]) / 100
    taux_int_2 = float(account[sup_rate]) / 100
    taux_ircm = float(account[ircm_rate]) / 100
    tva = float(account[tva_rate]) / 100
    frais_fixe = int(frais)
    comp_dec_epargne = int(int_epargne)

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
    calcul['IRCM'].append(ceil(res))

    # 18
    calcul['FRAIS_FIXES'].append(frais_fixe)

    inter = frais_fixe * tva

    calcul['TVA'].append(ceil(inter))

    # inter = [calcul[l] for l in list(calcul.keys())[:-1]]
    # val = list(map(sum, zip(*inter)))[0]

    val_total = calcul[int_inf][-1] + calcul[int_sup][-1] - calcul['TVA'][-1] - calcul['FRAIS_FIXES'][-1] - \
                calcul['IRCM'][-1]

    calcul['TOTAL'].extend(["", val_total])

    calcul[int_inf].insert(0, taux_int_1)
    calcul[int_sup].insert(0, taux_int_2)
    calcul['IRCM'].insert(0, taux_ircm)
    calcul['FRAIS_FIXES'].insert(0, "")
    calcul['TVA'].insert(0, tva)

    return calcul, cols_calcul


def whole_process(data_filter):
    result_data = computation_first_table(data_filter)
    compute = computation_first_table(result_data)

    return result_data, compute
