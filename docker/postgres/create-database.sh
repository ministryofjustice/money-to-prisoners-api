#!/bin/bash

echo "****** CREATING VIS DATABASE ******"
gosu postgres postgres --single <<- EOSQL
   CREATE DATABASE mtp_api ENCODING 'UTF8';
EOSQL
echo ""
echo "****** VIS DATABASE CREATED ******"
