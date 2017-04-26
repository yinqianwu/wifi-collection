import sys
import json
import os
import numpy
import bisect
import csv
import sqlite3


class DataPointReader(object):
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
                ts = m['$timestamp']
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

# class DataPointWriterReader(DataPointReader):
#     def __init__(self, keys, dataDir, outDir, dataType):
#         super(DataPointWriterReader, self).__init__(keys, dataDir, dataType)
#         self.outFile =  open(os.path.join(outDir, dataType + '.csv'), 'w')
#         self.writer = None
#         self.columns = None

#     def add_row(self, keyV, keyNamesV, _, objMap):
#         ts = objMap['$timestamp']
#         outMap = {k : v for k, v in objMap.iteritems() if not(k.startswith('@') or  k.startswith('$') or (type(v) == dict) or (type(v) == list))}
#         for k, v in zip(keyNamesV, keyV):
#             outMap[k] = v
#         outMap['timestamp'] = ts
#         if self.writer is None:
#             kk = outMap.keys()
#             self.writer = csv.DictWriter(self.outFile, fieldnames= kk)
#             self.writer.writeheader()
#             self.columns = kk
#         else:
#             outMap = {k : v for k, v in outMap.iteritems() if k in self.columns}
#         self.writer.writerow(outMap)


class DataPointWriterReader(DataPointReader):
    def __init__(self, keys, dataDir, outDb, dataType):
        super(DataPointWriterReader, self).__init__(keys, dataDir, dataType)
        self.outFile =  outDb
        self.cursor = outDb.cursor()
        self.columns = None
        self.keyToPos = None
        self.dataBuffer = []

    def add_row(self, keyV, keyNamesV, _, objMap):
        ts = objMap['$timestamp']
        outMap = {k : v for k, v in objMap.iteritems() if not(k.startswith('@') or  k.startswith('$') or (type(v) == dict) or (type(v) == list))}
        for k, v in zip(keyNamesV, keyV):
            outMap[k] = v
        outMap['timestamp'] = ts
        if self.columns is None:
            kk = outMap.keys()
            self.columns = kk
            self.table_from_map(outMap)
        else:
            outMap = {k : v for k, v in outMap.iteritems() if k in self.columns}
        self.store_line(outMap)

    def table_from_map(self, outMap):
        dataStr = ''
        for k, v in outMap.iteritems():
            if k == 'timestamp':
                t = 'UNSIGNED BIG INT'
            elif type(v) == int:
                t = 'INT'
            elif type(v) == float:
                t = 'REAL'
            else:
                t = 'text'
            dataStr += str(k) + ' ' + t + ','
        dataStr = dataStr.rstrip(',')
        createStr = 'CREATE TABLE {0} ({1});'.format(self.dataType, dataStr)
        # print createStr
        self.keyToPos = outMap.keys()
        self.cursor.execute(createStr)
        insertString = '?,' * len(outMap)
        insertString = insertString.rstrip(',')
        self.queryString = 'INSERT INTO {0} VALUES ({1})'.format(self.dataType, insertString)

    def store_line(self, outLine):
        outTuple =  tuple([outLine[k] if k in outLine.keys() else None for k in  self.keyToPos])
        self.dataBuffer.append(outTuple)
        if len(self.dataBuffer) >= 1000:
            # print self.queryString
            self.cursor.executemany(self.queryString, self.dataBuffer)
            self.outFile.commit()
            self.dataBuffer = []


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
# outDir = sys.argv[2]

outDir = sqlite3.connect('example.db')

apReader = DataPointWriterReader(['macAddress', 'name'], dataDir, outDir, 'AccessPointDetails')
macToApName = {}

for k, ts, dataType, m in apReader.generator():
    mac, ap = k
    macToApName[mac] = ap
    apReader.add_row([ap], ['apName'],'AccessPointDetails', m)


apReader = DataPointWriterReader([extract_variable_key, extract_variable_subkey], dataDir, outDir, 'ClientTraffics')

for k, ts, dataType, m in apReader.generator():
    mac, wlan = k
    apName = macToApName.get(mac)
    apReader.add_row([apName, wlan], ['apName', 'wlan'], 'ClientTraffics', m)

apReader = DataPointWriterReader([extract_variable_key, extract_variable_subkey], dataDir, outDir, 'ClientCounts')

for k, ts, dataType, m in apReader.generator():
    mac, wlan = k
    apName = macToApName.get(mac)
    apReader.add_row([apName, wlan], ['apName', 'wlan'], 'ClientCounts', m)

antennaToApMap = {}
apReader = DataPointWriterReader(['apName', 'baseRadioMac', 'slotId'], dataDir, outDir, 'RadioDetails')
for k, ts, dataType, m in apReader.generator():
    ap, mac, slot =  k
    antennaToApMap[mac] = ap
    apReader.add_row(list(k), ['apName', 'baseRadioMac', 'slotId'], 'RadioDetails', m)

apReader = DataPointWriterReader(["apName", 'baseRadioMac'], dataDir, outDir, 'Radios')

for k, ts, dataType, m in apReader.generator():
    apReader.add_row(list(k), ["apName", 'baseRadioMac'],'Radios', m)

apReader = DataPointWriterReader(['macAddress', 'slotId'], dataDir, outDir, 'RFCounters')

for k, ts, dataType, m in apReader.generator():
    mac, slot = k
    ap = antennaToApMap.get(mac)
    keys = [ap, mac, slot]
    apReader.add_row(keys, ["apName", 'baseRadioMac', 'slotId'], 'RFCounters', m)

apReader = DataPointWriterReader(['macAddress', 'slotId'], dataDir, outDir, 'RFStats')

for k, ts, dataType, m in apReader.generator():
    mac, slot = k
    ap = antennaToApMap.get(mac)
    keys = [ap, mac, slot]
    apReader.add_row(keys, ["apName", 'baseRadioMac', 'slotId'], 'RFStats', m)



clientToApMap = {}

apReader = DataPointWriterReader(['apName', "apMacAddress", "apSlotId", 'macAddress'], dataDir, outDir, 'ClientDetails')
for k, timestamp, dataType, m in apReader.generator():
    ap, apMac, apSlotId, mac  = k
    if mac not in clientToApMap.keys():
        clientToApMap[mac] =  []

    tsVector = [t for t, _ in clientToApMap[mac]]
    index = bisect.bisect(tsVector, timestamp)
    clientToApMap[mac].insert(index, (timestamp, (ap, apMac, apSlotId)))

    apReader.add_row(list(k), ["apName", 'baseRadioMac', 'slotId', 'clientMac'], 'ClientDetails', m)

apReader = DataPointWriterReader(['macAddress'], dataDir, outDir, 'ClientStats')
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
    apReader.add_row(list(ap) + [mac], ["apName", 'baseRadioMac', 'slotId', 'clientMac'], 'ClientStats', m)



