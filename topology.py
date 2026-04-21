"""
topology.py
-----------
Mininet topology for the SDN Topology Change Detector project.
Creates a linear chain of 3 switches, each with 2 hosts attached.
Uses OpenFlow 1.3 and connects to a remote Ryu controller on port 6653.

Topology:
  h1 -- s1 -- s2 -- s3 -- h5
  h2 /         |         \ h6
              h3
              h4
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.cli import CLI


class LinearTopoWithHosts(Topo):
    """
    Linear topology: has 3 switches in a chain.
    Each switch has 2 hosts attached.
    s1 -- s2 -- s3
    """

    def build(self):
        # --- Create 3 switches ---
        s1 = self.addSwitch('s1', cls=OVSKernelSwitch, protocols='OpenFlow13')
        s2 = self.addSwitch('s2', cls=OVSKernelSwitch, protocols='OpenFlow13')
        s3 = self.addSwitch('s3', cls=OVSKernelSwitch, protocols='OpenFlow13')

        # --- Create 6 hosts (2 per switch) ---
        h1 = self.addHost('h1', ip='10.0.0.1/24')
        h2 = self.addHost('h2', ip='10.0.0.2/24')
        h3 = self.addHost('h3', ip='10.0.0.3/24')
        h4 = self.addHost('h4', ip='10.0.0.4/24')
        h5 = self.addHost('h5', ip='10.0.0.5/24')
        h6 = self.addHost('h6', ip='10.0.0.6/24')

        # --- Link hosts to their switches ---
        # bw=10 = 10 Mbps bandwidth, delay='5ms' for realistic latency
        self.addLink(h1, s1, cls=TCLink, bw=10, delay='5ms')
        self.addLink(h2, s1, cls=TCLink, bw=10, delay='5ms')
        self.addLink(h3, s2, cls=TCLink, bw=10, delay='5ms')
        self.addLink(h4, s2, cls=TCLink, bw=10, delay='5ms')
        self.addLink(h5, s3, cls=TCLink, bw=10, delay='5ms')
        self.addLink(h6, s3, cls=TCLink, bw=10, delay='5ms')

        # --- Link switches together (the backbone) ---
        # These are the links we will bring DOWN for Scenario 2
        self.addLink(s1, s2, cls=TCLink, bw=100, delay='2ms')
        self.addLink(s2, s3, cls=TCLink, bw=100, delay='2ms')


def run():
    """Build and start the Mininet network."""
    setLogLevel('info')

    topo = LinearTopoWithHosts()

    # RemoteController points to Ryu running on localhost port 6653
    net = Mininet(
        topo=topo,
        controller=RemoteController('c0', ip='127.0.0.1', port=6653),
        switch=OVSKernelSwitch,
        link=TCLink,
        autoSetMacs=True   # assigns clean readable MACs: 00:00:00:00:00:01 etc.
    )

    net.start()
    info('\n*** Topology started. Switches: s1-s2-s3, Hosts: h1-h6\n')
    info('*** Ryu controller expected at 127.0.0.1:6653\n')
    info('*** Type "exit" or Ctrl+D to stop the network\n\n')

    CLI(net)   # drops you into the Mininet CLI

    net.stop()


if __name__ == '__main__':
    run()
