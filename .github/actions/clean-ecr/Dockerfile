FROM python:3-alpine
COPY entrypoint.py /usr/local/bin/clean-ecr
RUN set -ex && \
  chmod +x /usr/local/bin/clean-ecr \
  && \
  pip install --upgrade setuptools pip wheel \
  && \
  pip install awscli
ENTRYPOINT ["clean-ecr"]
