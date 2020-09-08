#!/bin/bash

/wait-for-it.sh db:5432 -- python /app/run.py serve
