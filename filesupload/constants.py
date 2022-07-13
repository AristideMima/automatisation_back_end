# Columns definitions
from django.http import JsonResponse
import re


# Computation names
debit = "DEBIT"
credit = "CREDIT"
normal_sold = "SOLDES"
sold_day = "SOLDES JOUR"
day = "NOMBRE DE JOURS"
debit_number = "DEBIT NOMBRES"
credit_number = "CREDIT NOMBRES"
sold_number = "SOLDES NOMBRES"
mvt_first_saving = "MVT à 2,45% 1"
mvt_second_saving = "MVT à 2,45% 2"


comptable = "Date Comptable"
agence = "Code Agence"
valeur = "Date de Valeur"
compte = "N° compte"
cle = "Cle compte"
intitule = "Intitulé compte"
libelle = "Libellé Opération"
code = "Code Opération"
sens = "Sens"
montant = "Montant"
datesold = "Date Solde"
sold = "Solde"
net = "Net Client"
comdec = "Com. Decouvert"
commvt = "Com. de compte"
frais = "Frais fixes"
tva = "Tva"

intdeb1 = "Int Deb 1"
intdeb2 = "Int Deb 2"
intdeb3 = "Int Deb 3"
tintdeb1 = "Taux Int Deb 1"
tintdeb2 = "Taux Int Deb 2"
tintdeb3 = "Taux Int Deb 3"

tcomdec = "Taux Com. Decouvert"
tcommvt = "Taux Com. de compte"
tfrais = "Taux Frais fixes"
ttva = "Taux Tva"

intinf = "Int inf"
intsup = "Int sup"
tintinf = "Taux Int inf"
tintsup = "Taux Int sup"
tircm = "Taux Ircm"

ircm = "Ircm"
valeurCredit = "Valeur Crédit"
datedeb = "Date Deb"
datefin = "Date Fin"
typecompte = "Type de compte"

# File headers definition

colhistoric = [comptable, agence, valeur, compte, cle, intitule, libelle, code, sens, montant]

colsold = [agence, compte, cle, datesold, sold]
colsoldshort = [compte, sold]

coljournalcourant = [agence, compte, cle, net, comdec, commvt, frais, tva, intdeb1, intdeb2, intdeb3]

coljournalepargne = [agence, compte, cle, net, intinf, intsup, ircm, frais, tva]

colautorisation = [agence, compte, cle, montant, datedeb, datefin]

colratecourant = [agence, compte, cle, tintdeb1, tintdeb2, tintdeb3, ttva, tcomdec, tcommvt]

colrateepargne = [agence, compte, cle, ttva, tintinf, tintsup, tircm]

pathcourant = 'static/courant/'
pathepargne = 'static/epargne/'

default_response_upload = JsonResponse({"message": "Les fichiers ne respectent pas le format requis"}, status=500)

default_type_loading = "rates"
default_option_courant = "courant"

rename_cols_courant = {compte: "num_account", tcomdec: "dec_rate", tcommvt: "com_rate", ttva: "tva_rate",
                       tintdeb1: "int1_rate", tintdeb2: "int2_rate", tintdeb3: "int3_rate"}

rename_cols_epargne = {compte: "num_account", tintinf: "inf_rate", tintsup: "sup_rate", tircm: "ircm_rate",
                       ttva: "tva_rate"}
drop_cols = [agence, cle]

table_courant = "filesupload_ratecourant"
table_epargne = "filesupload_rateepargne"


# Values
num_account = "num_account"
com_rate = "com_rate"
dec_rate = "dec_rate"
tva_rate = "tva_rate"
int1_rate = "int1_rate"
int2_rate ="int2_rate"
int3_rate = "int3_rate"

inf_rate = "inf_rate"
sup_rate = "sup_rate"
ircm_rate = "ircm_rate"

frais_courant = 5_000
frais_epargne = 2_000



#options
opt_taux_interet_debiteur_1 = "taux_interet_debiteur_1",
opt_taux_interet_debiteur_2 = "taux_interet_debiteur_2"
opt_taux_interet_debiteur_3 = "taux_interet_debiteur_3"
opt_taux_commision_mouvement = "taux_commision_mouvement"
opt_taux_commision_decouvert =  "taux_commision_decouvert"
opt_taux_tva = "taux_tva"

opt_taux_interet_inferieur = "taux_interet_inferieur"
opt_taux_interet_superieur =  "taux_interet_superieur"
opt_taux_ircm = "taux_ircm"

opt_frais = "frais_fixe"


mois = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'],

cols_var_courant = ["_int_1", "_int_2", "_int_3"]
cols_var_epargne = ["_int_inf", "_int_sup", "_ircm", "_tva"]


col_int_val = [
    'INTERÊTS DEBITEURS',
    # 'TVA/ INT DEBITEURS',
    'COMMISSION DE DECOUVERT',
    # 'TVA/ COM DECOUVERT',
    'COMMISSION DE MOUVEMENT',
    # 'TVA/ COM MVT',
    'FRAIS FIXES',
    # 'TVA/ FRAIS FIXES'
    'TVA',
    "TOTAUX"
]

col_int_val_epargne = [
    'INTERETS CREDITEURS',
    # 'TVA/ INT DEBITEURS',
    # 'TVA/ COM DECOUVERT',
    # 'TVA/ COM MVT',
    'FRAIS FIXES',
    # 'TVA/ FRAIS FIXES'
    'TVA',
    "TOTAUX"
]


#  =========== ALL DATA TEXT FOR LADDER ==============
table_saving = ["110", "140"]
auto_part = 35
reg_numb = "( )*(-)?([0-9\.,]+)(\d)+( )*[(TVA)(%)]*"
date_reg = '(\d\d)[-/](\d\d)[-/](\d\d(?:\d\d)?)'
regex_dict_val = {
    'code': '\d{5} -',
    'account': 'XAF-\d{11}-\d{2}',
    'dates': date_reg,
    'amount': '[\d\.]*\d+ XAF',
    'taxe_frais': 'TAXE/FRAIS{} ( )* TVA '.format(reg_numb),
    'taxe_com_mvt': 'TAXE/COMMISSION DE MOUVEMENT{}'.format(reg_numb),
    'com_mvt': 'COMMISSION DE MOUVEMENT({})+'.format(reg_numb),
    'com_dec': ' COMMISSION/PLUS FORT DECOUVERT({})+'.format(reg_numb),
    'int_debit': ' INTERETS DEBITEURS({})+'.format(reg_numb),
    'frais_fixe': 'FRAIS FIXES{}'.format(reg_numb),
    'net_deb': 'NET A DEBITER{}'.format(reg_numb),
    'solde_val': 'SOLDE EN VALEUR APRES AGIOS{}'.format(reg_numb),
    'tva': '(TAXE/INTERETS DEBITEURS|TAXE/COMM. PLUS FORT DECOUVERT|TAXE/COMMISSION DE MOUVEMENT|TAXE/FRAIS)({})+( )*'.format(reg_numb),
    'ircm': 'PRELEVEMENT LIBERATOIRE a compter du ( )* {}( )*({})+'.format(date_reg, reg_numb)
}


def get_value(colname, position, datas,  sep=" ", account=False):
    """
    :param: column name, position
    :return: corresponded value
    """
    value = re.search(regex_dict_val[colname], datas).group()
    if not account:
        value = value.split(sep)[position]
    return value


def get_interet(string_list, pos_string=0, pos_char=-1, sep="."):

    initial = string_list[pos_string].split()[pos_char]

    value = None

    if sep == ".":
        value = int(initial.replace(sep, ""))
    else:
        value = float(initial.replace(sep, "."))

    return value
