#!/usr/bin/env sh

docker run \
  --name postgres \
  --detach \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=mtp_api \
  circleci/postgres:10.10-alpine

sleep 10
