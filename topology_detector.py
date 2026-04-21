"""
topology_detector.py
--------------------
Ryu SDN controller application for the Topology Change Detector Project.

Two responsibilities:
  1. Learning switch  - handles packet_in, installs OpenFlow 1.3 flow rules
  2. Topology monitor - detects and logs switch/link/port join and leave events

Run with:
  ryu-manager --observe-links topology_detector.py

The flag --observe-links is REQUIRED. It activates Ryu's LLDP-based
topology discovery module (ryu.topology.switches), which is what fires
EventLinkAdd and EventLinkDelete events.
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.topology import event as topo_event
from ryu.topology.api import get_switch, get_link

import logging
import datetime
import os

# ── Log file setup ────────────────────────────────────────────────────────────
LOG_FILE = os.path.expanduser('~/topology_changes.log')

# Write to both terminal and log file simultaneously
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w'),  # overwrites on each run
        logging.StreamHandler()                    # also prints to terminal
    ]
)
logger = logging.getLogger('TopologyDetector')


class TopologyDetector(app_manager.RyuApp):
    """
    Ryu application: Learning Switch + Topology Change Detector.
    OpenFlow version: 1.3
    """

    # Tell Ryu this app uses OpenFlow 1.3
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(TopologyDetector, self).__init__(*args, **kwargs)

        # mac_to_port[datapath_id][mac_address] = port_number
        # Used by the learning switch to remember where each host lives
        self.mac_to_port = {}

        # Human-readable topology map for display
        # topology_map['switches'] = list of switch dpids
        # topology_map['links']    = list of (src_dpid, dst_dpid) tuples
        self.topology_map = {'switches': [], 'links': []}

        logger.info('=' * 60)
        logger.info('Topology Change Detector started')
        logger.info('Log file: %s', LOG_FILE)
        logger.info('=' * 60)

    # ── Helper: install a flow rule on a switch ───────────────────────────────

    def add_flow(self, datapath, priority, match, actions, idle_timeout=0, hard_timeout=0):
        """
        Install a flow rule (match + action) on the given switch (datapath).

        Args:
            datapath     : the switch object
            priority     : higher number = higher priority
            match        : OFPMatch object defining what packets to match
            actions      : list of actions to apply (e.g. output to port)
            idle_timeout : remove rule after N seconds of inactivity (0 = never)
            hard_timeout : remove rule after N seconds regardless (0 = never)
        """
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Instructions wrap actions in OpenFlow 1.3
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout
        )
        datapath.send_msg(mod)

    # ── Event 1: Switch connects to controller ────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """
        Fired when a switch first connects to the controller.
        We install a table-miss flow rule: any unmatched packet -> send to controller.
        This is what causes packet_in events to happen.
        """
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        logger.info('[SWITCH CONNECTED] dpid=%016x', dpid)

        # Table-miss rule: match anything (empty match), lowest priority (0)
        # Action: send to controller so we can learn the MAC address
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, priority=0, match=match, actions=actions)
        logger.info('[FLOW INSTALLED] Table-miss rule on dpid=%016x', dpid)

    # ── Event 2: Packet arrives that has no matching flow rule ────────────────

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """
        Fired when a switch sends an unmatched packet to the controller.
        We learn the source MAC -> port mapping, then:
          - If we know the destination: install a specific flow rule + forward
          - If we don't know: flood the packet to all ports
        """
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id
        in_port = msg.match['in_port']

        # Parse the raw packet bytes
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        # Ignore LLDP frames (used internally by Ryu topology discovery)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        src_mac = eth.src
        dst_mac = eth.dst

        # Initialise the MAC table for this switch if needed
        self.mac_to_port.setdefault(dpid, {})

        # Learn: remember which port this source MAC came from
        self.mac_to_port[dpid][src_mac] = in_port
        logger.info('[PACKET_IN] dpid=%016x  src=%s  dst=%s  in_port=%s',
                    dpid, src_mac, dst_mac, in_port)

        # Decide output port
        if dst_mac in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst_mac]
        else:
            out_port = ofproto.OFPP_FLOOD  # destination unknown: flood

        actions = [parser.OFPActionOutput(out_port)]

        # If we know the destination port, install a flow rule so future
        # packets for this src->dst pair go directly without hitting the controller
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst_mac, eth_src=src_mac)
            # idle_timeout=10: rule removed after 10s of no traffic
            self.add_flow(datapath, priority=1, match=match, actions=actions,
                          idle_timeout=10, hard_timeout=30)
            logger.info('[FLOW INSTALLED] dpid=%016x  %s->%s  out_port=%s',
                        dpid, src_mac, dst_mac, out_port)

        # Send the current packet out (it arrived before the rule existed)
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        )
        datapath.send_msg(out)

    # ── Topology Events (require --observe-links flag) ────────────────────────

    @set_ev_cls(topo_event.EventSwitchEnter)
    def switch_enter_handler(self, ev):
        """A new switch joined the topology."""
        switch = ev.switch
        dpid = switch.dp.id
        ports = [p.port_no for p in switch.ports]

        self.topology_map['switches'].append(dpid)
        logger.info('[TOPO CHANGE] SWITCH JOINED  dpid=%016x  ports=%s', dpid, ports)
        self._print_topology()

    @set_ev_cls(topo_event.EventSwitchLeave)
    def switch_leave_handler(self, ev):
        """A switch left or disconnected from the topology."""
        switch = ev.switch
        dpid = switch.dp.id

        if dpid in self.topology_map['switches']:
            self.topology_map['switches'].remove(dpid)
        logger.info('[TOPO CHANGE] SWITCH LEFT    dpid=%016x', dpid)
        self._print_topology()

    @set_ev_cls(topo_event.EventLinkAdd)
    def link_add_handler(self, ev):
        """A new link between two switches was discovered."""
        link = ev.link
        src_dpid = link.src.dpid
        dst_dpid = link.dst.dpid
        src_port = link.src.port_no
        dst_port = link.dst.port_no

        entry = (src_dpid, dst_dpid)
        if entry not in self.topology_map['links']:
            self.topology_map['links'].append(entry)

        logger.info('[TOPO CHANGE] LINK ADDED     s%s(port%s) --> s%s(port%s)',
                    src_dpid, src_port, dst_dpid, dst_port)
        self._print_topology()

    @set_ev_cls(topo_event.EventLinkDelete)
    def link_delete_handler(self, ev):
        """A link between two switches went down."""
        link = ev.link
        src_dpid = link.src.dpid
        dst_dpid = link.dst.dpid
        src_port = link.src.port_no
        dst_port = link.dst.port_no

        entry = (src_dpid, dst_dpid)
        if entry in self.topology_map['links']:
            self.topology_map['links'].remove(entry)

        logger.info('[TOPO CHANGE] LINK REMOVED   s%s(port%s) --> s%s(port%s)',
                    src_dpid, src_port, dst_dpid, dst_port)
        self._print_topology()

    @set_ev_cls(topo_event.EventPortAdd)
    def port_add_handler(self, ev):
        """A port was added to a switch."""
        port = ev.port
        logger.info('[TOPO CHANGE] PORT ADDED     dpid=%016x  port=%s',
                    port.dpid, port.port_no)

    @set_ev_cls(topo_event.EventPortDelete)
    def port_delete_handler(self, ev):
        """A port was removed from a switch."""
        port = ev.port
        logger.info('[TOPO CHANGE] PORT DELETED   dpid=%016x  port=%s',
                    port.dpid, port.port_no)

    # ── Helper: print current topology state ─────────────────────────────────

    def _print_topology(self):
        """Print a summary of the current known topology to terminal and log."""
        logger.info('--- Current Topology Map ---')
        logger.info('  Switches : %s', self.topology_map['switches'])
        logger.info('  Links    : %s', self.topology_map['links'])
        logger.info('----------------------------')
