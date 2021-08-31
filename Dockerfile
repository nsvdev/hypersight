FROM ubuntu:18.04
FROM python:3.7.0


WORKDIR /app

ADD requirements.txt /app

RUN set -ex && \
  pip install --no-cache-dir -r requirements.txt

ADD . /app

USER nobody

CMD ["/bin/sh", "docker-entrypoint.sh"]
