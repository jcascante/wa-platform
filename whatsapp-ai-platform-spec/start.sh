#!/bin/bash
cd /root/wa-platform
set -a
source .env
set +a
rm -f wa.db
nohup uvicorn main:app --port 8000 > server.log 2>&1 &
echo $! > server.pid
sleep 2
cat server.log
