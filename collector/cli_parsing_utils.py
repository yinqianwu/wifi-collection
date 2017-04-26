import json
import itertools

t = '''WLAN ID          Interface          Network Admission Control          Radio Policy
-------          -----------        --------------------------         ------------
 1               management           Disabled                          None
 2               management           Disabled                          None

*AP3600 with 802.11ac Module will only advertise first 8 WLANs on 5GHz radios.

AP Name             Slots  AP Model             Ethernet MAC       Location          Port  Country  Priority
------------------  -----  -------------------  -----------------  ----------------  ----  -------  --------
AP2                  2     AIR-CAP3702I-E-K9    f4:0f:1b:58:58:94  default location  1     BE       1
'''

t = '''
 Name               PID   Priority     CPU Use   (usr/sys)% hwm   CPU   Reaper

 System Reset Task  1529   (240/  7)        0     (  0/  0)%   0    7
 reaperWatcher      1528   (  3/ 96)        0     (  0/  0)%   0    0   I
 osapiReaper        1527   ( 10/ 94)        0     (  0/  0)%   0    0   I
 TempStatus         1526   (240/  7)        0     (  0/  0)%   0    4   I
 pktDebugSocketTask 1508   (255/  1)        0     (  0/  0)%   0    1
 webauthRedirect    1507   (240/  7)        0     (  0/  0)%   0    8
 emWeb              1506   (240/  7)        0     (  0/  0)%  19    3   T 300
 Bonjour_Msg_Task   1502   (174/ 32)        0     (  0/  0)%   0    8
 Bonjour_Process_Ta 1503   (174/ 32)        0     (  0/  0)%   0    6
 Bonjour_Socket_Tas 1504   (240/  7)        0     (  0/  0)%   0    4
 portalMsgTask      1500   (240/  7)        0     (  0/  0)%   0    2
 portalMonitorMsgTa 1501   (240/  7)        0     (  0/  0)%   0    3
 portalSockTask     1499   (240/  7)        0     (  0/  0)%   0    9
 PMIPV6_Thread_3    1498   (240/  7)        0     (  0/  0)%   0    9
 PMIPV6_Thread_2    1497   (240/  7)        0     (  0/  0)%   0    9
 PMIPV6_Thread_1    1496   (240/  7)        0     (  0/  0)%   0    9
 PMIPV6_Thread_0    1495   (240/  7)        0     (  0/  0)%   0    9
 hotspotTask        1494   (100/ 60)        0     (  0/  0)%   0    3
 ipv6SocketTask     1493   (240/  7)        0     (  0/  0)%   0    1
 IPv6_Msg_Task      1492   (174/ 32)        0     (  0/  0)%   0    6

'''


def indent(line):
    n = 0
    for l in line:
        if (l == ' '):
            n+=1
        else:
            break
    return n

def parse_indented_block(linesList, baseIndent):
    blockTitle = None
    lastName = None
    retMap = {}
    keyValMark = '....'
    while (len(linesList) > 0):
        line = linesList[0]
        line = line.rstrip('\n').rstrip('\r')
        ind = indent(line)
        line =  line[ind:]
        consumeLine = True
        numNonWhiteChars = sum([ 1 if c != ' ' else 0 for c in line])
        # print repr(line)
        # print ind

        if numNonWhiteChars == 0:
            pass
        elif line[0] == '.':
            assert(lastName is not None)
            val = line[line.rfind(keyValMark) + len(keyValMark):]
            retMap[lastName] += val.lstrip(' ')
        elif (ind > baseIndent):
            # assert(blockTitle is not None)
            blockMap = parse_indented_block(linesList, ind)
            if blockTitle is None:
                for k, v in blockMap.items():
                    retMap[k] = v
            else:
                retMap[blockTitle] =  blockMap
            # blockTitle = None
            consumeLine = False
        elif ind < baseIndent:
            return retMap
        elif (keyValMark not in line):
            # assert(blockTitle is None)
            blockTitle = line
        else:

            name = line[: line.find(keyValMark)]
            val = line[line.rfind(keyValMark) + len(keyValMark):]
            val = val.rstrip(' ').lstrip(' ')
            retMap[name] = val
            lastName = name
        if (consumeLine):
            linesList.pop(0)
    return retMap

def parse_details(linesList):
    return parse_indented_block(linesList, indent(linesList[0]))


class DecodingTable:
    def __init__(self, headerLine, lLine):
        firstDash = None
        self.ranges = []
        for i in range(0, len(lLine)):
            if lLine[i] == ' ':
                if firstDash is not None:
                    self.ranges.append((firstDash, i))
                    firstDash = None
            elif lLine[i] == '-':
                if firstDash is None:
                    firstDash = i
        if (firstDash is not None):
            self.ranges.append((firstDash, len(lLine)))
        self.columnNames = self._process_row(headerLine)
        self.rows = []


    def _process_row(self, line):
        retRow = []
        for beg, end in self.ranges:
            cName =  line[beg : min(end, len(line))]
            cName = cName.rstrip(' ').lstrip(' ')
            assert(len(cName) > 0)
            retRow.append(cName)
        return retRow

    def process_row(self, line):
        self.rows.append(self._process_row(line))

    def results_map(self):
        retMap = {}
        for i in range(0, len(self.columnNames)):
            cName = self.columnNames[i]
            data = [r[i] for r in self.rows]
            retMap[cName] = data
        return retMap

def indexed_results_map(rawMap, indexColumn):
    indCol = rawMap[indexColumn]
    retMap = {}
    for i in range(0, len(indCol)):
        key = indCol[i]
        dataMap = {k :rawMap[k][i] for k in rawMap.keys() if k != indexColumn}
        retMap[key] = dataMap
    return retMap





def parse_summary_maps(linesList):
    lastPossibleHeader = None
    outVec = []
    nextH = None
    decodingTable = None
    for line in linesList:
        line = line.rstrip('\n').rstrip('\r')
        if (len(line) == 0):
            if (decodingTable is not None):
                outVec.append(decodingTable.results_map())
                decodingTable = None
        elif ('---' in line):
            assert (decodingTable is None)
            assert (lastPossibleHeader is not None)
            decodingTable = DecodingTable(lastPossibleHeader, line)
        elif (decodingTable is not None):
            decodingTable.process_row(line)
        else:
            lastPossibleHeader = line
    return outVec



def iterate_combinations(strFormat, argVec):
    ll = list(itertools.product(*argVec))
    return [strFormat.fomat(*t) for t in ll]


def parse_cpu_load(cpuStr):
    lines = cpuStr.split('\n')
    targetStr = 'Individual CPU load:'
    for l in lines:
        if targetStr in l:
            l = l[(l.find(targetStr) + len(targetStr)):]
            l = l.rstrip('\r')
            tokens = l.split(',')
            retList = []
            for t in tokens:
                assert('/' in t)
                tt = t.split('/')
                def parse_cpu_usage(usStr):
                    assert('%' in usStr)
                    usStr = usStr.lstrip(' ').rstrip(' ')
                    usStr = usStr.rstrip('%')
                    return int(usStr)
                avgUse = parse_cpu_usage(tt[0])
                maxUse = parse_cpu_usage(tt[1])
                retList.append((avgUse, maxUse))
            return retList


def parse_csv_table(csvStr):
    lines =  csvStr.split('\n')
    boundaries = []
    def find_first_not_space(inStr, firstInd):
        for i in range(firstInd, len(inStr)):
            if inStr[i] != ' ':
                return i
        return None

    def line_to_list(line, boundaries):
        retList = []
        for i in range(0, len(boundaries) -1):
            rawData = line[boundaries[i]:boundaries[i+1]]
            rawData = rawData.rstrip(' ').lstrip(' ')
            retList.append(rawData)
        return retList
    lines = [l.lstrip(' ').rstrip('\r') for l in lines]
    lines = [l for l in lines if len(l) > 0]
    lines = lines[1:]
    curChar = 0
    firstLine = lines[0]
    totLen =  len(firstLine)
    while (curChar is not None):
        firstEmpty =  firstLine.find('  ', curChar)
        if (firstEmpty == -1):
            nextChar = None
        else:
            nextChar = find_first_not_space(firstLine, firstEmpty)
        boundaries.append(curChar)
        curChar = nextChar
    boundaries.append(totLen)
    headers = line_to_list(firstLine, boundaries)
    content = []
    for l in lines[1:]:
        if (len(l) == 0):
            continue
        content.append(line_to_list(l, boundaries))
    retMap = {}
    for i in range(0, len(headers)):
        retMap [headers[i]] = [c[i] for c in content]
    return retMap


def parse_processes_cpu(cliStr):
    rawMap = parse_csv_table(cliStr)
    m = indexed_results_map(rawMap, 'Name')
    # def compute_cpu_perc(rawStr):
    #     #  "(  0/  0)%"
    #     rawStr = rawStr.rstrip('%')
    #     rawStr = rawStr.rstrip(')').lstrip('(')
    #     tokens = rawStr.split('/')
    #     tokens = [int(t.rstrip(' ').lstrip(' ')) for t in tokens]
    #     return sum(tokens)
    retMap = {k: int(v['CPU Use']) for  k, v in m.items()}
    return retMap
if __name__ == '__main__':

    # linesList = t.split('\n')

    # # r = parse_indented_block(linesList, indent(linesList[0]))
    # r = parse_summary_maps(linesList)

    # m = indexed_results_map(r[1], 'AP Name')
    m = parse_processes_cpu(t)

    print (json.dumps(m, indent = 2))
