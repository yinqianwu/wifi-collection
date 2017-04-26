import sys
sys.path.append('../collector')

import commonlib.sln_params_parsing as sln_params_parsing
from commonlib.sln_logging import SlnLogging
import logging

import asyncio
from concurrent.futures import ProcessPoolExecutor
from pysnmp.hlapi.asyncio import *
from pysnmp.entity.rfc3413.oneliner import cmdgen
import pysnmp.entity.rfc3413
from pysnmp.smi import builder, view, compiler, error

from pysnmp.carrier.asyncore.dgram import udp, udp6, unix
from pyasn1.codec.ber import decoder
import asyncio
from pysnmp.proto import api

import subprocess
import time
import os
import yaml
import pyasn1
import json
import socket

@asyncio.coroutine
def run(mibsList, config, mibView):
    snmpEngine = SnmpEngine()
    mibBuilder = builder.MibBuilder()
    dumbmibView = view.MibViewController(mibBuilder)
    curDataModel = {}

    snmpEngine.setUserContext(mibViewController=dumbmibView)
    # identityQueue = [v for v in mibsList]
    identityQueue = [cmdgen.MibVariable(v).resolveWithMib(mibView).getOid() for v in mibsList]
    MibScalar, MibTableColumn = mibView.mibBuilder.importSymbols('SNMPv2-SMI', 'MibScalar', 'MibTableColumn')

    curOid = identityQueue.pop(0)
    mibName = ObjectIdentity(curOid).resolveWithMib(mibView).prettyPrint()
    prefix = config['data_prefix']
    outFile = config['outFile']


    print ('New MIB: ' + mibName)
    curVarBinds = (ObjectType(ObjectIdentity(curOid)),)
    lastOid = None
    while True:
        if config['v3User'] is None:
            authData = CommunityData(config['community_data'], mpModel=1)
        else:
            authData = UsmUserData(userName=config['v3User'],
                privKey=config['v3PrivK'],
                authKey=config['v3AuthK'],
                authProtocol = eval(config['v3AuthP']),
                privProtocol = eval(config['v3PrivP'])
                )

        errorIndication, errorStatus, errorIndex, \
            varBindTable = yield from bulkCmd(snmpEngine,
                authData,
                UdpTransportTarget((config['ip'], config['port'])),
                ContextData(),
                0, 30,
                * curVarBinds,
                lookupMib = False)

        if errorIndication:
            print(errorIndication)
            continue
        elif errorStatus:
            print('%s: %s at %s' % (
                    hostname,
                    errorStatus.prettyPrint(),
                    errorIndex and varBindTable[0][int(errorIndex)-1][0] or '?'
                )
            )
        else:
            endOfMib = False
            for varBindRow in varBindTable:
                for varBind in varBindRow:
                    for name, val in varBindRow:
                        name = ObjectIdentity(name).resolveWithMib(mibView)
                        try:
                            complete = ObjectType(name, val).resolveWithMib(mibView)
                        except pysnmp.smi.error.SmiError as e:
                            print (prefix + ':' + str(e))
                            continue
                        name, val = complete
                        ###table name and index
                        modName, lastName, indices = name.getMibSymbol()
                        mibNode = name.getMibNode()
                        diplayedVal = val.prettyPrint()
                        if isinstance(mibNode, MibTableColumn):
                            pmodName, psymName, pindices = mibView.getParentNodeName(name)
                            # print (psymName[-2] + ' : ' + str(indices))
                            tableName = psymName[-2]
                            if (tableName not in curDataModel):
                                curDataModel[tableName] = {}
                            key =  '.'.join([t.prettyPrint() for t in list(indices)])
                            if (key not in curDataModel[tableName]):
                                curDataModel[tableName][key] = {}
                            curDataModel[tableName][key][lastName] = diplayedVal
                            # for l in list(indices):
                            #     print (type(l))
                        else:
                            curDataModel[lastName] = diplayedVal
                        ##############
                        oid = name.getOid()

                        if (not curOid.isPrefixOf(oid)) or (oid == lastOid):
                            endOfMib = True
                            break
                        lastOid = oid
                        if val is not None:
                            outStr = ('%s = %s' % (name.prettyPrint(), val.prettyPrint()))
                        else:
                            outStr = ('%s = NA' % (name.prettyPrint()))
                        # outFile.write(str(int(time.time())) + ':' + outStr + '\n')
                if endOfMib: break



            if not endOfMib:
                curVarBinds = varBindTable[-1]
            else:
                if (len(identityQueue) == 0):
                    identityQueue = [cmdgen.MibVariable(v).resolveWithMib(mibView).getOid() for v in mibsList]
                    print ('{1}:Sleeping for {0} seconds'.format(config['check_interval'], prefix))
                    curDataModel['timeStamp'] = int(time.time() * 1000)
                    outFile.write(json.dumps(curDataModel) + '\n')
                    outFile.flush()
                    curDataModel = {}
                    yield from asyncio.sleep(config['check_interval'])
                    # time.sleep(config['check_interval'])
                curOid = identityQueue.pop(0)
                mibName = ObjectIdentity(curOid).resolveWithMib(mibView).prettyPrint()
                print (prefix + ':New MIB: ' + mibName)
                curVarBinds = (ObjectType(ObjectIdentity(curOid)),)
    snmpEngine.transportDispatcher.closeDispatcher()


class EchoServerProtocol:

    def __init__(self, mibView, wlcMap):
        self.mibView = mibView
        self.wlcMap = wlcMap

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        msgVer = int(api.decodeMessageVersion(data))
        ip, port = addr
        if ip not in self.wlcMap:
            print ('Enexpected trap from ' + ip)
            return
        wlcName, outFile = self.wlcMap[ip]
        if msgVer in api.protoModules:
            pMod = api.protoModules[msgVer]
        else:
            print('Unsupported SNMP version %s' % msgVer)
            return
        reqMsg, wholeMsg = decoder.decode(
            data, asn1Spec=pMod.Message(),
            )

        print('Notification message from : ' + str(wlcName))
        reqPDU = pMod.apiMessage.getPDU(reqMsg)

        if reqPDU.isSameTypeWith(pMod.TrapPDU()):
            outMap = {}
            outMap['timeStamp'] = int(time.time() * 1000)
            if msgVer == api.protoVersion1:
                varBinds = pMod.apiTrapPDU.getVarBindList(reqPDU)
            else:
                varBinds = pMod.apiPDU.getVarBindList(reqPDU)
            # print('Var-binds:')
            for name, val in varBinds:

                valType = val.getName()
                # print (valType)
                if valType == 'value':
                    v = val.getComponent()
                    n = v.getName()
                    c = v.getComponent()
                    mibVal = str(c.getComponent())
                    mibType = c.getName()
                else:
                    continue

                try:
                    name = ObjectIdentity(name).resolveWithMib(self.mibView)
                except pysnmp.smi.error.SmiError as e:
                    print (prefix + ':' + str(e))
                    continue
                except pyasn1.type.error.ValueConstraintError as e:
                    reducedT = tuple(list(name.asTuple())[:-1])
                    name = ObjectIdentity(reducedT).resolveWithMib(self.mibView)


                # print ('*' * 20)

                # print (wlcName + ':'+ name.prettyPrint())
                # print (wlcName + ':'+ mibType)

                if mibType == 'objectID-value':
                    # print (mibVal)
                    inName  = ObjectIdentity(mibVal).resolveWithMib(self.mibView)
                    outMap['eventType'] = inName.prettyPrint()
                    # print (wlcName + ':'+ inName.prettyPrint())
                else:
                    outMap[name.prettyPrint()] = mibVal
                    # print (wlcName + ':'+ mibVal)
                # print ('-' * 20)
            # print (json.dumps(outMap, indent = 2))
            outFile.write(json.dumps(outMap) + '\n')
            outFile.flush()

class EchoServerProtocolFactory:
    def __init__(self, mibView, wlcMap):
        self.mibView = mibView
        self.wlcMap = wlcMap

    def __call__(self):
        return EchoServerProtocol(self.mibView, self.wlcMap)


class CheckValInSet:
    def __init__(self, validVals):
        self.valid = set(validVals)
        self.errStr = 'Invalid argument {0}: value has to be one of ' + ','.join(validVals)

    def __call__(self, arg):
        if (arg in self.valid):
            return (True,'')
        return (False, self.errStr.format(arg))


checkAuthAlgo = CheckValInSet(['usmNoAuthProtocol','usmHMACMD5AuthProtocol','usmHMACSHAAuthProtocol'])
checkPrivAlgo = CheckValInSet(['usmNoPrivProtocol','usmDESPrivProtocol','usm3DESEDEPrivProtocol','usmAesCfb128Protocol','usmAesCfb192Protocol','usmAesCfb256Protocol'])

snmpAgentArgs = [
    sln_params_parsing.ConfDescription("ip",['ip'], validationFunc = sln_params_parsing.is_valid_host_or_ip),
    sln_params_parsing.ConfDescription("check_interval",['check_interval'], constDefault = 30),
    sln_params_parsing.ConfDescription("community_data",['community_data'], constDefault = 'public'),
    sln_params_parsing.ConfDescription("port",['port'], constDefault = 161),
    sln_params_parsing.ConfDescription("data_prefix",['data_prefix'], failIfMissing = False),
    sln_params_parsing.ConfDescription("data_dir",['data_dir'], constDefault = 'data'),
    sln_params_parsing.ConfDescription('v3User', ['v3User'], failIfMissing = False),
    sln_params_parsing.ConfDescription('v3AuthK', ['v3AuthK'], failIfMissing = False),
    sln_params_parsing.ConfDescription('v3PrivK', ['v3PrivK'], failIfMissing = False),
    sln_params_parsing.ConfDescription('v3AuthP', ['v3AuthP'], failIfMissing = False, validationFunc = checkAuthAlgo),
    sln_params_parsing.ConfDescription('v3PrivP', ['v3PrivP'], failIfMissing = False, validationFunc = checkPrivAlgo),
    sln_params_parsing.ConfDescription('traps_listening_port', ['traps_listening_port'], failIfMissing = False)
]

mibsListArgs = [
    sln_params_parsing.ConfDescription("mib",['mib']),
    sln_params_parsing.ConfDescription("node", ['node'],  failIfMissing = False)
]






if __name__ == '__main__':

    try:
        config_fd = open(sys.argv[1])
    except IOError as err:
        log.error("Unable to open config YAML file. {}".format(err))
        sys.exit(1)

    inputParameters = yaml.load(config_fd)

    mibBuilder = builder.MibBuilder()

    pythonMibsDir = os.path.join(os.path.expanduser("~"), '.pysnmp' , 'mibs')

    mibBuilder.addMibSources(builder.DirMibSource(pythonMibsDir))

    mibsList = []

    for filename in os.listdir(pythonMibsDir):
        if not filename.endswith('.py'):
            continue
        mibsList.append(filename[:-3])

    mibBuilder.loadModules(
        *tuple(list(mibsList))
        )

    mibView = view.MibViewController(mibBuilder)

    oidsList = []
    for i, mibConfig in enumerate(inputParameters['snmp_mibs']):
        mibParser = sln_params_parsing.ParamsMap(
            descriptionMap=mibsListArgs,
            defaultValues={},
            loggingString='mib_' + str(i))
        mibDesc = mibParser.read_input_values(mibConfig)
        mib = mibDesc['mib']
        nodeName = mibDesc['node']
        if nodeName is not None:
            oid, label, suffix = mibView.getNodeName((nodeName,), mib)
        else:
            oid = cmdgen.MibVariable(mib).resolveWithMib(mibView).getOid()
        oidsList.append(oid)


    log = SlnLogging.get_sln_logger('snmp', logging.INFO)

    serverConfigs = []

    wlcMap = {}
    for i, serverConfig in enumerate(inputParameters['snmp_agents']):
        serverConfParser = sln_params_parsing.ParamsMap(
            descriptionMap=snmpAgentArgs,
            defaultValues={},
            loggingString='agent_' + str(i))
        serverDesc = serverConfParser.read_input_values(serverConfig)

        prefix = serverDesc['data_prefix']
        dataDir = serverDesc['data_dir']
        if not os.path.exists(dataDir):
            os.makedirs(dataDir)
        outFileN = dataDir +'/data_' + prefix + '_' + str(int(time.time())) + '.dat'
        outFile = open(outFileN, 'w')
        ip = socket.gethostbyname(serverDesc['ip'])
        wlcMap[ip] = (prefix, outFile)
        serverDesc['outFile'] = outFile
        serverConfigs.append(serverDesc)
    trapListeningPorts = [c['traps_listening_port'] for c in serverConfigs if c['traps_listening_port'] is not None]
    trapListeningPorts = list(set(trapListeningPorts))

    #######need to reenable commit hash logging
    # if False:
    #     commitHash = args.git_commit_hash
    # elif "GIT_COMMIT_HASH" in os.environ and os.environ["GIT_COMMIT_HASH"]:
    #     commitHash = os.environ["GIT_COMMIT_HASH"]
    # else:
    #     commitHash = subprocess.check_output('git rev-parse  HEAD', shell=True)
    #     commitHash = commitHash.decode("utf-8")
    #     commitHash = commitHash.rstrip('\n')

    # log.info("Commit hash: {0}".format(commitHash))

    loop = asyncio.get_event_loop()

    for i,config in enumerate(serverConfigs):
        asyncio.async(run(oidsList, config, mibView))

    if len(trapListeningPorts) > 1:
        print ('Only one trap listening port is supported')
        sys.exit(-1)
    if (len(trapListeningPorts) > 0):
        listen = loop.create_datagram_endpoint(
            EchoServerProtocolFactory(mibView, wlcMap), local_addr=('0.0.0.0', trapListeningPorts[0]))
        transport, protocol = loop.run_until_complete(listen)
    else:
        loop.run_forever()

