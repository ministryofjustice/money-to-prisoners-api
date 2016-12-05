FROM ubuntu:trusty

# setup environment
RUN echo "Europe/London" > /etc/timezone && dpkg-reconfigure --frontend noninteractive tzdata
RUN locale-gen "en_GB.UTF-8"
ENV LC_CTYPE=en_GB.UTF-8
ENV TERM=xterm

# install libraries
RUN apt-get update && apt-get install -y software-properties-common python-software-properties
RUN apt-get update && apt-get install -y build-essential curl gettext git libpcre3-dev libpq-dev ntp

# pre-create directories
WORKDIR /app
RUN mkdir -p mtp_api/assets
RUN mkdir -p mtp_api/assets-static
RUN mkdir -p static
RUN mkdir -p media

# install python
RUN apt-get install -y python3-all python3-all-dev python3-setuptools python3-pip python-pip python3.4-venv
RUN /usr/bin/python3 -m venv venv
RUN venv/bin/pip install -U setuptools pip wheel

# install node.js
RUN curl -sL https://deb.nodesource.com/setup_7.x | bash -
RUN apt-get install -y nodejs
RUN npm set progress=false
RUN npm cache clean
RUN curl -L https://npmjs.org/install.sh | bash  # npm -g install npm fails currently
RUN [ -e /usr/bin/node ] || ln -s /usr/bin/nodejs /usr/bin/node

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
CMD venv/bin/uwsgi --ini conf/uwsgi/api.ini
