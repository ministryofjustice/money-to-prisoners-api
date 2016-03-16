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
RUN mkdir -p /app/mtp_api/assets
RUN mkdir -p /app/static

RUN pip3 install -U setuptools pip wheel virtualenv
RUN virtualenv -p python3.4 venv

# cache python packages, unless requirements change
ADD ./requirements /app/requirements
RUN venv/bin/pip install -r requirements/docker.txt

ADD . /app
RUN make build python_requirements=requirements/docker.txt

EXPOSE 8080
EXPOSE 8800
CMD make uwsgi python_requirements=requirements/docker.txt
