#!/bin/bash

set -eux

docker-compose down
docker-compose pull
docker-compose build --pull --no-cache
docker-compose up -d
