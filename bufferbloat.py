from mininet.topo import Topo
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.net import Mininet
from mininet.log import lg, info
from mininet.util import dumpNodeConnections
from mininet.cli import CLI

from subprocess import Popen, PIPE
from time import sleep, time
from multiprocessing import Process
from argparse import ArgumentParser

from monitor import monitor_qlen

import sys
import os
import math
import numpy as np

parser = ArgumentParser(description="Bufferbloat tests")
parser.add_argument('--bw-host', '-B', type=float,
                    help="Bandwidth of host links (Mb/s)", default=1000)
parser.add_argument('--bw-net', '-b', type=float,
                    help="Bandwidth of bottleneck (network) link (Mb/s)", required=True)
parser.add_argument('--delay', type=float,
                    help="Link propagation delay (ms)", required=True)
parser.add_argument('--dir', '-d', help="Directory to store outputs", required=True)
parser.add_argument('--time', '-t', type=int,
                    help="Duration (sec) to run the experiment", default=10)
parser.add_argument('--maxq', type=int,
                    help="Max buffer size of network interface in packets", default=100)
parser.add_argument('--cong', help="Congestion control algorithm to use", default="reno")
args = parser.parse_args()


class BBTopo(Topo):
    "Simple topology for bufferbloat experiment."

    def build(self, n=2):
        # Create two hosts and one switch
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        switch = self.addSwitch('s0')

        # Link: h1 <-> switch at high bandwidth (host link)
        self.addLink(h1, switch,
                     bw=args.bw_host,
                     delay="%sms" % args.delay,
                     use_htb=True)

        # Link: switch <-> h2 at bottleneck bandwidth, with queue limit
        self.addLink(switch, h2,
                     bw=args.bw_net,
                     delay="%sms" % args.delay,
                     max_queue_size=args.maxq,
                     use_htb=True)


def start_iperf(net):
    "Start a long-lived TCP flow from h1 to h2"
    h1 = net.get('h1')
    h2 = net.get('h2')
    info("* Starting iperf server on h2...\n")
    server = h2.popen("iperf -s -w 16m", shell=True)
    sleep(1)
    info("* Starting iperf client on h1...\n")
    client = h1.popen("iperf -c %s -t %d -w 16m" % (h2.IP(), args.time), shell=True)
    return server, client


def start_qmon(iface, interval_sec=0.1, outfile="q.txt"):
    monitor = Process(target=monitor_qlen,
                      args=(iface, interval_sec, outfile))
    monitor.start()
    return monitor


def start_ping(net):
    "Start a high-rate ping train from h1 to h2, logging RTTs every 0.1s"
    h1 = net.get('h1')
    h2 = net.get('h2')
    ping_file = os.path.join(args.dir, 'ping.txt')
    # -i 0.1 -> interval 100ms, run until killed
    cmd = "ping %s -i 0.1 > %s" % (h2.IP(), ping_file)
    info("* Starting ping train h1->h2...\n")
    ping_proc = h1.popen(cmd, shell=True)
    return ping_proc


def start_webserver(net):
    "Launch a simple HTTP server on h1 (serving index.html)"
    h1 = net.get('h1')
    info("* Starting webserver on h1...\n")
    proc = h1.popen("python webserver.py", shell=True)
    sleep(1)
    return [proc]


def bufferbloat():
    if not os.path.exists(args.dir):
        os.makedirs(args.dir)
    # Set TCP CC algorithm
    os.system("sysctl -w net.ipv4.tcp_congestion_control=%s" % args.cong)

    topo = BBTopo()
    net = Mininet(topo=topo, host=CPULimitedHost, link=TCLink)
    net.start()
    dumpNodeConnections(net.hosts)
    net.pingAll()

    # Start queue monitoring on the switch interface facing h2 (s0-eth2)
    qmon = start_qmon(iface='s0-eth2',
                      outfile=os.path.join(args.dir, 'q.txt'))

    # Start long-lived TCP flow and ping probe
    iperf_server, iperf_client = start_iperf(net)
    ping_proc = start_ping(net)

    # Start web server on h1
    web_procs = start_webserver(net)

    # Measure webpage fetch times from h2
    h2 = net.get('h2')
    h1 = net.get('h1')
    fetch_times = []

    start_time = time()
    while True:
        now = time()
        elapsed = now - start_time
        if elapsed > args.time:
            break
        # Every 5 seconds, do 3 sequential fetches
        for i in range(3):
            cmd = "curl -o /dev/null -s -w %{time_total} http://%s:8000/index.html" % h1.IP()
            proc = h2.popen(cmd, stdout=PIPE, shell=True)
            out = proc.communicate()[0].decode().strip()
            try:
                fetch_times.append(float(out))
                info("Fetch %d: %s s\n" % (i+1, out))
            except:
                info("Warning: could not parse fetch time: %s\n" % out)
        sleep(5)

    # Compute and report statistics
    if fetch_times:
        avg = np.mean(fetch_times)
        std = np.std(fetch_times)
        print("Average fetch time: %.3f s, std dev: %.3f s" % (avg, std))
    else:
        print("No fetch times recorded.")

    # Clean up
    ping_proc.terminate()
    iperf_client.terminate()
    iperf_server.terminate()
    qmon.terminate()
    for p in web_procs:
        p.terminate()

    net.stop()
    # Kill any leftover webserver.py processes
    Popen("pgrep -f webserver.py | xargs kill -9", shell=True).wait()


if _name_ == '_main_':
    bufferbloat()