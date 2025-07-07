#!/bin/bash

# Note: Mininet must be run as root. So invoke this script with sudo.
if [ "$EUID" -ne 0 ]; then
  echo "⚠️  Please run as root: sudo $0"
  exit 1
fi

# duração total do experimento (s)
TIME=90

# largura de banda do gargalo (Mb/s)
BW_NET=1.5

# para obter RTT mínimo de ~20 ms:
# cada link h1–s0 e s0–h2 recebe 5 ms de delay → 
# one-way = 5+5=10 ms → RTT = 2*10 ms = 20 ms
DELAY=5

# porta do iperf (se precisar mudar; não é usada no código atual)
IPERF_PORT=5001

for QSIZE in 20 100; do
    DIR=bb-q${QSIZE}
    echo "=== Experimento q=$QSIZE pkt → pasta $DIR ==="

    # (re)cria pasta de saída
    rm -rf $DIR && mkdir -p $DIR

    # roda o bufferbloat.py
    python3 bufferbloat.py \
        --bw-net ${BW_NET} \
        --delay ${DELAY} \
        --dir ${DIR} \
        --time ${TIME} \
        --maxq ${QSIZE} \
        --cong reno

    # plota fila e RTT
    echo "--- Gerando gráfico de fila (q=${QSIZE})"
    python3 plot_queue.py -f ${DIR}/q.txt -o reno-buffer-q${QSIZE}.png

    echo "--- Gerando gráfico de RTT (q=${QSIZE})"
    python3 plot_ping.py  -f ${DIR}/ping.txt -o reno-rtt-q${QSIZE}.png

    echo
done

echo "✅ Todos os experimentos concluídos."
