import sys
import json
import os
import numpy
import bisect


class DataPointReader:
    def __init__(self, keys, dataDir, dataType):
        self.keys = keys
        self.fileName = os.path.join(dataDir, dataType + '.json')
        self.dataType =  dataType
        self.dataDir = dataDir
        filesList = []
        for filename in os.listdir(dataDir):
            if not filename.endswith('.json'):
                continue
            if not filename.startswith(dataType):
                continue
            if ('_' not in filename):
                #this is the "current" file, so we make sure it is the last in the list
                filesList.append((filename, sys.maxint))
                continue
            filenum = int(filename[filename.find('_') + 1: filename.find('.')])
            filesList.append((filename, filenum))
        filesList = sorted(filesList, key = lambda x : x[1])
        self.filesList = [f[0] for f in filesList]


    def fd_to_read(self):
        if len(self.filesList) == 0:
            return None
        f = self.filesList.pop(0)
        filename =  os.path.join(self.dataDir, f)
        print ('Processing ' + filename)
        return open(filename)


    def generator(self):
        fd = self.fd_to_read()
        while fd is not None:
            for l in fd:
                l = l.rstrip('\n')
                m = json.loads(l)
                # print m
                ts = m['timestamp']
                keys = []
                invalid = False
                for k in self.keys:
                    if hasattr(k, '__call__'):
                        key = k(m)
                    else:
                        key = m.get(k)
                    if key is None:
                        invalid = True
                        break
                    keys.append(key)
                if not invalid:
                    yield (tuple(keys), ts, self.dataType, m)
            fd = self.fd_to_read()


class Node:
    def __init__(self):
        self.content = {}
        self.sons = {}

    def add_content(self, contentType, content):
        if contentType not in self.content.keys():
            self.content[contentType] = []
        self.content[contentType].append(content)

    def add_node(self, keys, keyNames, contentType, content):
        assert(len(keys) == len(keyNames))
        if len(keys) == 0:
            self.add_content(contentType, content)
            return
        keyVal = keys.pop(0)
        keyName = keyNames.pop(0)
        key = (keyName, keyVal)
        if key not in self.sons.keys():
            self.sons[key] =  Node()
        self.sons[key].add_node(keys, keyNames, contentType, content)

    def print_node(self):
        retMap  = {}
        retMap['content'] = self.content
        retMap['sons'] = {str(k): v.print_node() for k,v in self.sons.items()}
        return retMap

    def retrieve_nodes_for_key(self, keyNames, valName):
        assert(len(keyNames) >= 1)
        retMap = {}
        keyName = keyNames[0]
        keyNames = keyNames[1:]
        lastCall = len(keyNames) == 0
        for k, v in self.sons.iteritems():
            kk, kv =  k
            if kk == keyName:
                newValName =  valName + [kv]
                if lastCall:
                    retMap[tuple(newValName)] = v
                else:
                    retMap.update(v.retrieve_nodes_for_key(keyNames, newValName))
        return retMap



class InformationForKey:
    def __init__(self, staticInfo):
        self.staticInfo = staticInfo
        self.dataToCorrelate = {}
        self.minTs = None
        self.maxTs = 0

    def process(self, ts, infoType, info):
        if infoType not in self.dataToCorrelate.keys():
            self.dataToCorrelate[infoType] = []
        self.dataToCorrelate[infoType].append((ts, info))


    def summarize(self):
        deltaList = []
        for k in self.dataToCorrelate.keys():
            self.dataToCorrelate[k] = sorted(self.dataToCorrelate[k], key = lambda x : x[0])
        for k, v in self.dataToCorrelate.items():
            print 'Dynamic information of type ' + str(k) + ('*' * 30)
            previousTs = 0
            for ts, data in v:
                print ('-' * 30)
                delta = ts - previousTs
                if previousTs != 0:
                    # deltaList.append(delta)
                    print 'Delta min: ' + str(delta / 60000.0)
                # if delta != 0:
                print json.dumps(data, indent = 2)
                previousTs =  ts
                self.minTs = ts if self.minTs is None else min(ts, self.minTs)
                self.maxTs = max(ts, self.maxTs)

        print 'Min to max ts ' + str((self.maxTs - self.minTs) / 60000) + '--------------------------------------------------------------------'
        return deltaList




# DEVICE
# ACCESSPOINT
# MAPLOCATION
# SSID
# VIRTUALDOMAIN
# GUEST

def extract_variable_key(jsonObj):
    keyType = jsonObj["type"]
    if keyType == 'ACCESSPOINT':
        return jsonObj['key']
    return None
def extract_variable_subkey(jsonObj):
    keyType = jsonObj["type"]
    if keyType == 'ACCESSPOINT':
        return jsonObj['subkey']
    return None


dataDir = sys.argv[1]


baseNode = Node()

apReader = DataPointReader(['macAddress', 'name'], dataDir, 'AccessPointDetails')

macToApName = {}

for k, ts, dataType, m in apReader.generator():
    mac, ap = k
    macToApName[mac] = ap
    baseNode.add_node([ap], ['apName'],'AccessPointDetails', m)

baseNode.print_node()

apReader = DataPointReader([extract_variable_key, extract_variable_subkey], dataDir, 'ClientTraffics')

for k, ts, dataType, m in apReader.generator():
    mac, wlan = k
    apName = macToApName.get(mac)
    baseNode.add_node([apName, wlan], ['apName', 'wlan'], 'ClientTraffics', m)

apReader = DataPointReader([extract_variable_key, extract_variable_subkey], dataDir, 'ClientCounts')

for k, ts, dataType, m in apReader.generator():
    mac, wlan = k
    apName = macToApName.get(mac)
    baseNode.add_node([apName, wlan], ['apName', 'wlan'], 'ClientCounts', m)

antennaToApMap = {}
apReader = DataPointReader(['apName', 'baseRadioMac', 'slotId'], dataDir, 'RadioDetails')
for k, ts, dataType, m in apReader.generator():
    ap, mac, slot =  k
    antennaToApMap[mac] = ap
    baseNode.add_node(list(k), ['apName', 'baseRadioMac', 'slotId'], 'RadioDetails', m)

apReader = DataPointReader(["apName", 'baseRadioMac'], dataDir, 'Radios')

for k, ts, dataType, m in apReader.generator():
    baseNode.add_node(list(k), ["apName", 'baseRadioMac'],'Radios', m)

apReader = DataPointReader(['macAddress', 'slotId'], dataDir, 'RFCounters')

for k, ts, dataType, m in apReader.generator():
    mac, slot = k
    ap = antennaToApMap.get(mac)
    keys = [ap, mac, slot]
    baseNode.add_node(keys, ["apName", 'baseRadioMac', 'slotId'], 'RFCounters', m)

apReader = DataPointReader(['macAddress', 'slotId'], dataDir, 'RFStats')

for k, ts, dataType, m in apReader.generator():
    mac, slot = k
    ap = antennaToApMap.get(mac)
    keys = [ap, mac, slot]
    baseNode.add_node(keys, ["apName", 'baseRadioMac', 'slotId'], 'RFStats', m)



clientToApMap = {}

apReader = DataPointReader(['apName', "apMacAddress", "apSlotId", 'macAddress'], dataDir, 'ClientDetails')
for k, timestamp, dataType, m in apReader.generator():
    ap, apMac, apSlotId, mac  = k
    if mac not in clientToApMap.keys():
        clientToApMap[mac] =  []

    tsVector = [t for t, _ in clientToApMap[mac]]
    index = bisect.bisect(tsVector, timestamp)
    clientToApMap[mac].insert(index, (timestamp, (ap, apMac, apSlotId)))

    baseNode.add_node(list(k), ["apName", 'baseRadioMac', 'slotId', 'clientMac'], 'ClientDetails', m)

apReader = DataPointReader(['macAddress'], dataDir, 'ClientStats')
for k, timestamp, dataType, m in apReader.generator():
    mac = k[0]
    apVec = clientToApMap.get(mac)
    if apVec is None:
        ap = [None, None, None]
    else:
        tsVector = [t for t, _ in apVec]
        index = bisect.bisect(tsVector, timestamp)
        if index == 0:
            ap = [None, None, None]
        else:
            ts, ap = clientToApMap[mac][index -1]
    # if (ap == [None, None, None]):
    #     print 'No ap for ' + str(mac)
    # else:
    #     print 'Found for ' + str(mac) + ' is ' + str(ap)
    #     print apVec
    # print list(ap) + [mac]
    baseNode.add_node(list(ap) + [mac], ["apName", 'baseRadioMac', 'slotId', 'clientMac'], 'ClientStats', m)


# m = baseNode.print_node()

m = baseNode.retrieve_nodes_for_key(["apName", 'baseRadioMac', 'slotId'], [])

m = {str(k): v.print_node() for k,v in m.iteritems()}
print json.dumps(m, indent = 2)




# print 'Antenna  granularity data ' + ('=' * 30)
# dynamicInfo = [DataPointReader(['macAddress', 'slotId'], dataDir, 'RFCounters')
#                 ,DataPointReader(['macAddress', 'slotId'], dataDir, 'RFStats')]


# staticInfo = [DataPointReader(['baseRadioMac', 'slotId'], dataDir, 'RadioDetails')]


# deltas, counts  = correlate_info(staticInfo, dynamicInfo)

# print 'Access point granularity data ' + ('=' * 30)
# dynamicInfo = [DataPointReader(extract_variable_key, dataDir, 'ClientTraffics')
#                 ,DataPointReader(extract_variable_key, dataDir, 'ClientCounts')]

# staticInfo = [DataPointReader(['macAddress'], dataDir, 'AccessPointDetails')]


# deltas, counts  = correlate_info(staticInfo, dynamicInfo)



# print 'Client granularity data ' + ('=' * 30)
# dynamicInfo = [DataPointReader(['macAddress'], dataDir, 'ClientStats')
#                 ,DataPointReader(['macAddress'], dataDir, 'ClientDetails')]

# staticInfo = []


# deltas, counts  = correlate_info(staticInfo, dynamicInfo)

