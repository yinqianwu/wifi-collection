import sys
sys.path.append('../collector')

import collections
import socket
import commonlib.sln_params_parsing as sln_params_parsing


import pcapy
import dpkt
import yaml
import time

class TimeSeries:
    slotSize = 1
    def __init__(self, key):
        self.lastSlot = int(time.time())/self.slotSize
        self.count = 0
        self.key = ':'.join([str(l) for l in key])
        self.outFile = open(self.key + '.dat', 'w')

    def process_ts(self, timeStamp, bytes):
        slot =  int(timeStamp)/self.slotSize
        if slot == self.lastSlot:
            self.count += bytes
            # print str(self.key) + 'Bytes ' + str(self.count) + ' ' + str(bytes)
        else:
            self.log_tuple(self.lastSlot, self.count)
            for s in range(self.lastSlot + 1, slot):
                self.log_tuple(s, 0)
            self.lastSlot = slot
            self.count = bytes
    def log_tuple(self, slot, x):
        self.outFile.write(str(self.slotSize * slot) + ',' + str(x) + '\n')

class NetworkMonitor:
    def __init__ (self, clientList):
        self.clientList = []
        self.clientMap = {}
        for c in clientList:
            t = (socket.gethostbyname(c['ip']) , c['port'])
            print t
            self.clientMap[t] = TimeSeries(t)
            self.clientList.append(t)

    def start (self):
        # TODO: specify a device or select all devices
        dev = pcapy.findalldevs()[0]
        # dev = 'eth0'
        p = pcapy.open_live(dev, 65536, False, 1)
        filterProgram = ' or '.join('(port {1} and host {0})'.format(host, port) for host, port in self.clientList)
        print filterProgram
        p.setfilter(filterProgram)

        p.loop(-1, self.handle_packet)

    def handle_packet (self, header, data):
        # print dir(header)
        eth = dpkt.ethernet.Ethernet (data)
#        print "%04X" % eth.type

        if eth.type == dpkt.ethernet.ETH_TYPE_IP:
            ip = eth.data
            ip_data = ip.data
            srcIp = ip.src
            dstIp = ip.dst
            # print ip.src
            # print ip.dst
            if isinstance (ip_data, dpkt.udp.UDP):
                udp = ip_data
                srcPort = udp.sport
                dstPort = udp.dport
                # print srcPort
                # print dstPort
                pktLen = header.getlen()
                secEpoch, ms = header.getts()
                secEpoch += float(ms) / 1000000

                srcTuple = (socket.inet_ntop(socket.AF_INET, srcIp), srcPort)
                dstTuple = (socket.inet_ntop(socket.AF_INET, dstIp), dstPort)

                if srcTuple in self.clientMap.keys():
                    self.clientMap[srcTuple].process_ts(secEpoch, pktLen)
                elif dstTuple in self.clientMap.keys():
                    self.clientMap[dstTuple].process_ts(secEpoch, pktLen)
                else:
                    print 'Unknown tuple ' + str(srcTuple) + ' ' + str(dstTuple)
            else:
                print 'NON UDP'


snmpAgentArgs = [
    sln_params_parsing.ConfDescription("ip",['ip'], validationFunc = sln_params_parsing.is_valid_host_or_ip),
    sln_params_parsing.ConfDescription("check_interval",['check_interval'], constDefault = 30),
    sln_params_parsing.ConfDescription("community_data",['community_data'], constDefault = 'public'),
    sln_params_parsing.ConfDescription("port",['port'], constDefault = 161),
    sln_params_parsing.ConfDescription("data_prefix",['data_prefix'], failIfMissing = False),
    sln_params_parsing.ConfDescription("data_dir",['data_dir'], constDefault = 'data')
]

if __name__=="__main__":
    try:
        config_fd = open(sys.argv[1])
    except IOError as err:
        log.error("Unable to open config YAML file. {}".format(err))
        sys.exit(1)

    inputParameters = yaml.load(config_fd)
    serverConfigs = []

    for i, serverConfig in enumerate(inputParameters['snmp_agents']):
        serverConfParser = sln_params_parsing.ParamsMap(
            descriptionMap=snmpAgentArgs,
            defaultValues={},
            loggingString='agent_' + str(i))
        serverDesc = serverConfParser.read_input_values(serverConfig)
        serverConfigs.append(serverDesc)
    monitor = NetworkMonitor(serverConfigs)
    monitor.start()