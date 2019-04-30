FROM python:3-alpine

LABEL "com.github.actions.name" = "Clean ECR"
LABEL "com.github.actions.description" = "Delete branch images from ECR when PR is merged"
LABEL "com.github.actions.icon" = "trash"
LABEL "com.github.actions.color" = "orange"

COPY entrypoint.py /usr/local/bin/clean-ecr
RUN set -ex && \
  chmod +x /usr/local/bin/clean-ecr \
  && \
  pip install --upgrade setuptools pip wheel \
  && \
  pip install awscli

ENTRYPOINT ["clean-ecr"]
