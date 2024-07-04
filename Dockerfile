# https://hub.docker.com/_/python
FROM python:3.10-slim-bullseye

ENV PYTHONUNBUFFERED True
ENV APP_HOME /app
WORKDIR $APP_HOME

RUN apt-get update && \
    apt-get install -y libpq-dev gettext && \
    pip install psycopg2-binary

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

RUN python3 manage.py collectstatic --noinput
RUN python3 manage.py compilemessages

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
