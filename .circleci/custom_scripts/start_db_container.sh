#!/usr/bin/env sh

docker run \
  --name postgres \
  --detach \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=mtp_api \
  cimg/postgres:14.3

sleep 10
