FROM buildpack-deps:xenial

# setup environment
RUN apt-get update && apt-get install -y --no-install-recommends locales tzdata
RUN set -ex; echo en_GB.UTF-8 UTF-8 > /etc/locale.gen && locale-gen
ENV LANG=en_GB.UTF-8
ENV TZ=Europe/London
RUN timedatectl set-timezone Europe/London || true

# install libraries
RUN apt-get install -y --no-install-recommends software-properties-common build-essential rsync gettext python3-all-dev python3-venv

# install node.js
RUN curl -sL https://deb.nodesource.com/setup_8.x | bash -
RUN apt-get install -y --no-install-recommends nodejs
RUN npm set progress=false

# cleanup
RUN rm -rf /var/lib/apt/lists/*

# pre-create directories
WORKDIR /app
RUN set -ex; mkdir -p \
  mtp_api/assets \
  mtp_api/assets-static \
  static \
  media \
  spooler
RUN set -ex; chown www-data:www-data \
  media \
  spooler

# install virtual environment
RUN /usr/bin/python3 -m venv venv
RUN venv/bin/pip install -U setuptools pip wheel

# cache python packages, unless requirements change
ADD ./requirements requirements
RUN venv/bin/pip install -r requirements/docker.txt

# add app and build it
ADD . /app
RUN venv/bin/python run.py --requirements-file requirements/docker.txt build

# run uwsgi on 8080
EXPOSE 8080
EXPOSE 8800
ENV DJANGO_SETTINGS_MODULE=mtp_api.settings.docker
CMD venv/bin/python manage.py migrate --no-input && venv/bin/uwsgi --ini api.ini
