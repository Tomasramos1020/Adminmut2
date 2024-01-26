FROM python:3.7

ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN pip install --upgrade pip

COPY requirements.txt /app/

RUN pip install -r requirements.txt

RUN apt-get update
RUN apt-get install -y build-essential libblas-dev liblapack-dev

RUN pip install pandas==0.23.4

COPY /admincu/. /app 

COPY /admincu/migrations_extra/0003_auto_20180821_1213.py /usr/local/lib/python3.7/site-packages/django_afip/migrations/

COPY /admincu/migrations_extra/0016_auto_20180326_1129.py /usr/local/lib/python3.7/site-packages/django_mercadopago/migrations/

COPY /admincu/migrations_extra/0017_auto_20180424_1717.py /usr/local/lib/python3.7/site-packages/django_mercadopago/migrations/

COPY /admincu/migrations_extra/0018_auto_20180808_1242.py /usr/local/lib/python3.7/site-packages/django_mercadopago/migrations/

EXPOSE 8000



#CMD [ "gunicorn", "admincu.wsgi", "--bind", "0.0.0.0:8000", "--timeout", "1800", "--chdir=/app/admincu" ]

CMD [ "/app/admincu/manage.py", "runserver", "0.0.0.0:8000"]

