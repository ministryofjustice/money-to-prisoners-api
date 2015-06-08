FROM ubuntu:trusty

RUN echo "Europe/London" > /etc/timezone  &&  dpkg-reconfigure -f noninteractive tzdata

RUN apt-get update && \
    apt-get install -y software-properties-common python-software-properties

RUN add-apt-repository -y ppa:nginx/stable
RUN add-apt-repository -y ppa:chris-lea/node.js

RUN apt-get update && \
    apt-get install -y \
        build-essential git python3-all python3-all-dev python3-setuptools \
        supervisor curl nginx libpq-dev ntp ruby ruby-dev nodejs python3-pip
RUN service nginx stop && rm /etc/init.d/nginx

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 10

WORKDIR /app

RUN gem update rdoc
RUN npm install -g bower gulp
RUN gem install sass

ADD ./conf/uwsgi /etc/uwsgi

ADD ./conf/nginx/nginx.conf /etc/nginx/nginx.conf
ADD ./conf/nginx/sites-enabled /etc/nginx/sites-enabled
ADD ./conf/supervisor /etc/supervisor

ADD ./requirements/ /app/requirements/
RUN pip3 install -r requirements/dev.txt

ADD . /app
RUN bower install --allow-root

EXPOSE 80
EXPOSE 443
CMD ["supervisord", "-n"]
