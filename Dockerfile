FROM python:3.11-bullseye
COPY requirements.txt /tmp/
RUN apt update
RUN  pip install --upgrade pip
RUN pip install --requirement /tmp/requirements.txt
COPY . /tmp/
COPY callbacks/ /callbacks
COPY app_layout.py /
COPY app_prod.py /
EXPOSE 8050
CMD ["waitress-serve", "--host=0.0.0.0", "--port=8050", "app_prod:app.server"]

# CMD ["waitress-serve", "--host=0.0.0.0", "--port=8080", "--threads=8", "dashboard_prod:app.server"]