#!/bin/bash
cd /root/wa-platform
: "${WEBHOOK_SECRET:?set WEBHOOK_SECRET to the value returned by POST /me/webhook}"
nohup uvicorn example_customer_webhook:app --port 9000 > customer.log 2>&1 &
echo $! > customer.pid
sleep 2
cat customer.log
