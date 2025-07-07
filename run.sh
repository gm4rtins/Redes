#!/bin/bash
set -e

# só para garantir que estamos como root
if [ "$EUID" -ne 0 ]; then
  echo "⚠️  Rode com sudo: sudo $0"
  exit 1
fi

TIME=90
BW_NET=1.5
DELAY=5

for QSIZE in 20 100; do
    DIR=bb-q${QSIZE}
    echo "=== Experimento q=${QSIZE} → ${DIR} ==="

    # limpa qualquer resto de Mininet antes de criar a topologia
    mn -c

    rm -rf ${DIR} && mkdir -p ${DIR}

    python3 bufferbloat.py \
        --bw-net ${BW_NET} \
        --delay ${DELAY} \
        --dir ${DIR} \
        --time ${TIME} \
        --maxq ${QSIZE} \
        --cong reno

    echo "--- Plotando fila"
    python3 plot_queue.py -f ${DIR}/q.txt  -o reno-buffer-q${QSIZE}.png

    echo "--- Plotando RTT"
    python3 plot_ping.py  -f ${DIR}/ping.txt -o reno-rtt-q${QSIZE}.png

    echo
done

# Última limpeza geral (opcional)
mn -c

echo "✅ Todos os experimentos concluídos."
