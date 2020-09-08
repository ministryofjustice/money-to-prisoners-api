#!/bin/bash
# This entrypoint is only used in the development environment, not in test or prod

/wait-for-it.sh db:5432 -- python /app/run.py serve
