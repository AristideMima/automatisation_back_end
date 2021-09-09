# FROM postgres
# ENV POSTGRES_PASSWORD djoudken
# ENV POSTGRES_DB nano_credit
# COPY nano_credit.sql /docker-entrypoint-initdb.d/
# RUN python manage.py makemigrations
# RUN python manage.py migrate

FROM python:3.8.8-alpine
ENV PYTHONUNBUFFERED 1
RUN mkdir /djangoBackend
WORKDIR /djangoBackend
COPY requirements.txt /code/
EXPOSE 8000
RUN pip install -r requirements.txt
COPY . .

#COPY ./services/settings.py /code/services/services.py
#COPY ./automatisation/settings.py /code/automatisation/settings.py
#COPY ./.envcontainer /code/.env
#CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]




# FROM python:3
# ENV PYTHONUNBUFFERED 1
# RUN mkdir /backend
# WORKDIR /backend
# COPY requirements.txt /backend/
# EXPOSE 8000
# RUN pip install -r requirements.txt
# COPY . /backend/
# RUN python manage.py makemigrations
# RUN python manage.py migrate