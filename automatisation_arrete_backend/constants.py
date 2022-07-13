# PERSONAL GLOBAL CONSTANTS
from sqlalchemy import create_engine

db_type = "postgresql"
db_name = "automatisation"
db_user = "postgres"
db_password = "ArisPostgres237"
db_host = "localhost"
db_port = "5432"

database_url = '{postgresql}://{user}:{password}@{localhost}:5432/{database_name}'.format(
    postgresql=db_type,
    user=db_user,
    password=db_password,
    database_name=db_name,
    localhost=db_host
)

engine = create_engine(database_url, echo=False)


## Local

# PERSONAL GLOBAL CONSTANTS
from sqlalchemy import create_engine

# db_type = "postgresql"
# db_name = "automatisation"
# db_user = "aristide"
# db_password = "arispass"
# db_host = "localhost"
# db_port = "5432"
#
# database_url = '{postgresql}://{user}:{password}@{localhost}:5432/{database_name}'.format(
#     postgresql=db_type,
#     user=db_user,
#     password=db_password,
#     database_name=db_name,
#     localhost=db_host
# )
#
# engine = create_engine(database_url, echo=False)

