#!/bin/sh
exec gunicorn main:app --timeout 300 --bind 0.0.0.0:${PORT:-8080}
