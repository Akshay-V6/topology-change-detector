# SDN Topology Change Detector
This project implements an SDN-based topology change detector using Mininet and the Ryu OpenFlow controller. The controller dynamically monitors the network for switch joins/leaves, link additions/deletions, and port changes, logging all events in real time. It also functions as a learning switch, installing OpenFlow 1.3 flow rules reactively.

Built as part of the CN Mini Project.

## Author
Akshay V

## Implementation Notes
- Implemented using Ryu's topology discovery API (--observe-links)
- Uses reactive flow installation (learning switch behavior)
- Tested under link failure and recovery scenarios

## Topology
Linear chain of 3 switches (s1-s2-s3), each with 2 hosts attached (h1-h6).
- 6 hosts: h1-h6 with IPs 10.0.0.1 to 10.0.0.6
- 3 OVS switches running OpenFlow 1.3
- Remote Ryu controller on 127.0.0.1:6653

## Requirements
- Ubuntu 20.04
- Mininet 2.2.2
- Ryu 4.30
- Open vSwitch 2.13.8

## Setup & Execution

**Step 1 — Terminal 1, start Ryu controller first:**

    cd ~/topology-change-detector
    ryu-manager --observe-links topology_detector.py

**Step 2 — Terminal 2, start Mininet after Ryu is ready:**

    sudo python2 topology.py

**Note:** Always start Ryu before Mininet. The --observe-links flag is required for link event detection.

**Cleanup:**

    sudo mn -c

## Test Scenarios

### Scenario 1 — Normal Operation
Run pingall in Mininet CLI. Expect 0% packet loss with all switches and links detected.

### Scenario 2 — Link Failure and Recovery
Run the following commands in Mininet CLI:

    link s1 s2 down

Ryu logs LINK REMOVED event immediately. Run pingall — expect 53% dropped. Then:

    link s1 s2 up

Run pingall again — expect 0% dropped.

## Performance Observations

| Metric | Normal | Link Down |
|--------|--------|-----------|
| Ping reachability | 0% dropped | 53% dropped |
| iperf h1 to h6 | ~10 Mbits/sec | connect failed |
| Active links | 2 | 1 |

## Proof of Execution

### Scenario 1 — Normal Operation
![Terminal 1 Init](screenshots/Terminal_1_Init)
![Terminal 2 Init](screenshots/Terminal_2_Init.png)

### Scenario 2 — Link Failure
![Link Down Ryu](screenshots/Terminal_1_link_down.png)
![Link Down Mininet](screenshots/Terminal_2_link_down.png)

### Recovery
![Link Up Ryu](screenshots/Terminal_1_link_up.png)
![Link Up Mininet](screenshots/Terminal_2_link_up.png)

### iperf Results
![iperf](screenshots/Terminal_2_iperf_link_down.png)
![Recovered Throughput](screenshots/Terminal_2_recovered_thruput.png)

### Flow Tables
![Flow Tables](screenshots/Flow_Table.png)

### Wireshark — OpenFlow Messages
![Wireshark](screenshots/Wireshark_mininet_pingall.png)

## References
1. Ryu SDN Framework - https://ryu-sdn.org
2. Ryu Documentation - https://ryu.readthedocs.io
3. Mininet - http://mininet.org

## Conclusion
The system successfully detects topology changes in real time and adapts network behavior accordingly. It demonstrates how SDN enables centralized control and dynamic network management.   
5. OpenFlow 1.3 Specification - https://opennetworking.org
6. Ryu Topology API - https://github.com/faucetsdn/ryu/blob/master/ryu/topology/api.py
