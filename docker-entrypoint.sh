#!/bin/sh

echo "Waiting for mysql service start...";
# sleep 20;

export FLASK_APP=server
flask init-db


export FLASK_ENV=development
export FLASK_DEBUG=0
flask run --host=0.0.0.0