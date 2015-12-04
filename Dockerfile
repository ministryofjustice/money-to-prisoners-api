FROM ubuntu:trusty

RUN locale-gen "en_GB.UTF-8"
ENV LC_CTYPE=en_GB.UTF-8

RUN apt-get update && \
    apt-get install -y software-properties-common python-software-properties

RUN apt-get update && \
    apt-get install -y \
        build-essential git python3-all python3-all-dev python3-setuptools \
        curl libpq-dev ntp libpcre3-dev python3-pip python-pip

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 10

WORKDIR /app

ADD ./conf/uwsgi /etc/uwsgi

ADD ./requirements/ /app/requirements/
RUN pip3 install -r requirements/prod.txt

ADD . /app

RUN ./manage.py collectstatic --noinput

ADD ./docker_entrypoint.sh /app/docker_entrypoint.sh
RUN chmod 777 /app/docker_entrypoint.sh

EXPOSE 8080

CMD /app/docker_entrypoint.sh
