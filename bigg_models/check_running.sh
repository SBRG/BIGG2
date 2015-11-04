#!/bin/bash
source /Users/dbuser/bigg_production/env_production/bin/activate

if ps -A | grep -v grep | grep 'python -m bigg_models.server --port=8888'; then
    echo Running;
else
    python -m bigg_models.server --port=8888
fi
exit
