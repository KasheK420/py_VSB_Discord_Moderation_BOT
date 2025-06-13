#!/bin/bash

set -eux

echo "Activating virtual environment."
source ../.venv/bin/activate

echo "Starting bot."
../.venv/bin/python app.py