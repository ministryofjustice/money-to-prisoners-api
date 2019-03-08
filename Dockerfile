FROM buildpack-deps:bionic

# setup UK environment and install libraries and python
RUN set -ex; \
  apt-get update \
  && \
  DEBIAN_FRONTEND=noninteractive apt-get install \
  -y --no-install-recommends --no-install-suggests \
  -o DPkg::Options::=--force-confdef \
  locales tzdata \
  && \
  echo en_GB.UTF-8 UTF-8 > /etc/locale.gen \
  && \
  locale-gen \
  && \
  rm /etc/localtime \
  && \
  ln -s /usr/share/zoneinfo/Europe/London /etc/localtime \
  && \
  dpkg-reconfigure --frontend noninteractive tzdata \
  && \
  DEBIAN_FRONTEND=noninteractive apt-get install \
  -y --no-install-recommends --no-install-suggests \
  -o DPkg::Options::=--force-confdef \
  software-properties-common build-essential \
  gettext rsync libssl1.0-dev \
  python3-all-dev python3-setuptools python3-pip python3-wheel python3-venv \
  nodejs nodejs-dev node-gyp npm \
  chromium-browser \
  && \
  rm -rf /var/lib/apt/lists/* \
  && \
  npm set progress=false
ENV LANG=en_GB.UTF-8
ENV TZ=Europe/London

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
RUN set -ex; \
  /usr/bin/python3 -m venv venv && \
  venv/bin/pip install -U setuptools pip wheel

# cache python packages, unless requirements change
ADD ./requirements requirements
RUN venv/bin/pip install -r requirements/docker.txt

# add app and build it
ADD . /app
RUN set -ex; \
  venv/bin/python run.py --requirements-file requirements/docker.txt build

# run uwsgi on 8080
EXPOSE 8080
EXPOSE 8800
ENV DJANGO_SETTINGS_MODULE=mtp_api.settings.docker
CMD venv/bin/python manage.py migrate --no-input && venv/bin/uwsgi --ini api.ini
