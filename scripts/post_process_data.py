import sqlite3
import sys
import pandas
import datetime
import matplotlib.pyplot as plt

lastTs = pandas.to_datetime('8/22/2016', utc = True)


def datetime_to_epoch(dtStr):
    dt = pandas.to_datetime(dtStr, utc = True)
    b = dt.to_pydatetime()
    b = b.replace(tzinfo=None)
    return int((b-datetime.datetime.utcfromtimestamp(0)).total_seconds() * 1000)

def create_pandas(r, h):
    if len(r) == 0:
        return pandas.DataFrame()
    p = pandas.DataFrame(r, columns=h)
    # p = p[pandas.to_datetime(p['timestamp'], unit = 'ms', utc = True) < lastTs]
    p.index = pandas.to_datetime(p.pop('timestamp'), unit = 'ms', utc = True)
    # p = p - p.min()
    return p


class SqliteDb:
    def __init__(self, dbName):
        self.con = sqlite3.connect(dbName)
        self.con.text_factory = str
        self.cur = self.con.cursor()

    def execute_query(self, query):
        print query
        results = [l for l in self.cur.execute(query)]

        headers = [] if (len(results) == 0) else self.get_headers()
        return (headers , results)

    def get_headers(self):
        return list(map(lambda x: x[0], self.cur.description))

def check_frequency(db, keys, tableName, xlsWriter, where = None):
    keysQry = ''
    for k in keys:
        keysQry+= k + ','
    keysQry = keysQry.rstrip(',')
    whereStr = 'where ' + where if where is not None else ''

    apQueries = 'select timestamp, {0}  from {1} {2};'.format(keysQry, tableName, whereStr)

    h, r = db.execute_query(apQueries)

    df = pandas.DataFrame(r, columns=h)
    df = df[pandas.to_datetime(df['timestamp'], unit = 'ms', utc = True) < lastTs]

    ts = df['timestamp']

    minTs = ts.min()
    maxTs = ts.max()
    duration = (maxTs - minTs)

    interarrival = df.groupby(keys).timestamp.nunique()

    threshold = interarrival.quantile(0.4)
    thresholdHist = interarrival.quantile(0.01)

    avg = pandas.Series([(duration / 60000.0)/ (s + 1.0) for s in interarrival if s > thresholdHist])

    if avg.nunique() > 100:
        h = avg.value_counts(bins = 100)
    else:
        h = avg.value_counts()

    h = h.to_frame(tableName)
    h.sort_index(inplace = True)
    h.to_excel(xlsWriter, tableName)
    print 'threshold is ' + str(threshold)
    print 'Before filtering ' + str(interarrival.size)

    interarrival = interarrival[interarrival >= threshold]

    print 'After filtering ' + str(len(interarrival.index))

    return interarrival.reset_index(level=0, inplace=False)
    # return interarrival

def compute_histograms(outExcel, h, r, prefix):
    df = pandas.DataFrame(r, columns=h)
    df.set_index(['apName'], inplace=True)
    outLiersMap = {}
    for name, values in df.iteritems():
        binNum = values.nunique()
        if binNum == 1:
            h = values.value_counts()
        else:
            h = values.value_counts(bins =100)
        h = h.to_frame(name)
        h.sort_index(inplace = True)
        h.to_excel(outExcel, prefix + name)



def clients_stats_distribution(db, statsList, outExcel):
    outerSelect = ','.join(['avg({0}_{1})'.format(aggFun, stat) for aggFun, stat in statsList])
    innerSelect = ','.join(['{0}({1}) as {0}_{1}'.format(aggFun, stat) for aggFun, stat in statsList])
    query = 'select apName, {0} from (select timestamp, apName, {1} from ClientStats group by timestamp, apName) group by apName;'.format(outerSelect, innerSelect)
    h, r = db.execute_query(query)
    compute_histograms(outExcel, h, r, 'clnt_')


rfCountersFields = ['ackFailureCount',
'fcsErrorCount',
'failedCount',
'rtsFailureCount',
'rtsSuccessCount',
'retryCount']

def rf_counters_time_series(db, apName, tsFilter):
    outerSelect = ','.join(['sum({0}) / max(sum(txFrameCount) * 1.0, 1.0) as norm_{0}'.format(f) for f in rfCountersFields])
    query = 'select timestamp, {0} from RFCounters where apName == "{1}" {2} group by timestamp'.format(outerSelect, apName, tsFilter)
    h, r =  db.execute_query(query)
    return create_pandas(r, h)

def rf_counters_distr(db, outExcel):

    innerSelect = ','.join(['sum({0}) / max(sum(txFrameCount) * 1.0, 1.0) as norm_{0}'.format(f) for f in rfCountersFields])
    outerSelect = ','.join(['avg(norm_{0})'.format(f) for f in rfCountersFields])

    query = 'select apName, {0} from ( select apName, timestamp, {1} from RFCounters  group by apName, timestamp) group by apName;'.format(outerSelect, innerSelect)
    h, r =  db.execute_query(query)
    compute_histograms(outExcel, h, r, 'rfcnt')



def profile_specific_ap(db, selctedAp, firstTs, lastTs):
    tsFilter = ' '

    if (firstTs is not None):
        tsFilter += 'and timestamp > ' + str(firstTs) + ' '
    if (lastTs is not None):
        tsFilter += 'and timestamp < ' + str(lastTs) + ' '


    countsTimeSeries = 'select count, authCount, timestamp  from ClientCounts  where subkey == "All" and apName == "{0}" {1} order by timestamp;'.format(selctedAp, tsFilter)

    h, r = db.execute_query(countsTimeSeries)

    countsDfRaw = create_pandas(r, h)

    countsDf = countsDfRaw.groupby(level = 0).sum()


    # countsTimeSeries = 'select received, sent, throughput, timestamp  from ClientTraffics  where subkey == "All" and apName == "{0}" {1} order by timestamp;'.format(selctedAp, tsFilter)
    countsTimeSeries = 'select *  from ClientTraffics  where subkey == "All" and apName == "{0}" {1} order by timestamp;'.format(selctedAp, tsFilter)

    h, r = db.execute_query(countsTimeSeries)

    trafDf = create_pandas(r, h)



    radioDf = rf_counters_time_series(db, selctedAp, tsFilter);


    countsTimeSeries = 'select macAddress, dataRate, packetsSent, raPacketsDropped, rssi, snr, rtsRetries, rxBytesDropped, rxPacketsDropped, txBytesDropped, txPacketsDropped ,timestamp  from ClientStats  where apName == "{0}" {1};'.format(selctedAp, tsFilter)

    h, r = db.execute_query(countsTimeSeries)
    # clientsDf = pandas.DataFrame(r, columns=h)
    clientsDf = create_pandas(r, h)



    countsTimeSeries = 'select baseRadioMac, txUtilization, rxUtilization, channelUtilization, poorCoverageClients, timestamp from RFStats  where apName == "{0}" {1};'.format(selctedAp, tsFilter)

    h, r = db.execute_query(countsTimeSeries)
    radioStatsDf = create_pandas(r, h)
    if radioStatsDf.shape[0] > 0:
        radioStatsDf = radioStatsDf.groupby(level=0).sum()
        radioStatsDf[radioStatsDf < 0] = 0


    if clientsDf.shape[0] > 0:
        groupedClients = clientsDf.groupby(level = 0)
        # clientsDf['packetsSent'] = clientsDf['packetsSent'].apply(lambda x : x/1.0)

        # ([u'macAddress', u'dataRate', u'packetsSent', u'raPacketsDropped', u'rssi', u'snr', u'rtsRetries', u'rxBytesDropped', u'rxPacketsDropped', u'txBytesDropped', u'txPacketsDropped']

        meanClnt = groupedClients['snr', 'rssi'].mean()
        clientCounts = groupedClients['macAddress'].count()
        sumCltn = groupedClients[u'dataRate', u'packetsSent', u'raPacketsDropped', u'rtsRetries', u'rxBytesDropped', u'rxPacketsDropped', u'txBytesDropped', u'txPacketsDropped'].sum()

        # joinedC = groupedClients.mean()
        clientbasedStats =  pandas.concat([meanClnt, clientCounts, sumCltn], axis=1)
    else:
        clientbasedStats = pandas.DataFrame()

    return (clientsDf, trafDf, clientbasedStats, radioDf, radioStatsDf, countsDf)


if __name__ == '__main__':

    db = SqliteDb(sys.argv[1])
     # select apName, avg(snrT) from (select apName, avg(snr) as snrT, timestamp  from ClientStats group by timestamp, apName) group by apName;
    # baseNode.add_node(list(k), ['apName', 'baseRadioMac', 'slotId'], 'RadioDetails', m)
    selctedAp = None
    # selctedAp = 'ast03-12-cap13'
    selctedAp = 'rcdn9-21-cap8'
    # selctedAp = 'rcdn9-ewelling-APECC8.82BA.36C8'
    if selctedAp is None:
        outExcel = pandas.ExcelWriter('client_stats_dist.xlsx')

        client_stats = [
        ('count', 'macAddress'),
        ('avg', 'dataRate'),
        ('avg', 'packetsSent'),
        ('avg', 'raPacketsDropped'),
        ('avg', 'rssi'),
        ('min', 'rssi'),
        ('avg', 'snr'),
        ('min', 'snr'),
        ('avg', 'rtsRetries'),
        ('avg', 'rxBytesDropped'),
        ('avg', 'rxPacketsDropped'),
        ('avg', 'txBytesDropped'),
        ('avg', 'txPacketsDropped')]
        clients_stats_distribution(db, client_stats, outExcel)
        rf_counters_distr(db, outExcel)

        outExcel.save()

        fExcel = pandas.ExcelWriter('frequencies.xlsx')
        rfCnt = check_frequency(db, ["apName", 'baseRadioMac', 'slotId'], 'RFCounters', fExcel)
        clntTr = check_frequency(db, ['apName'], 'ClientTraffics', fExcel, 'subkey = "All"')
        clntCt = check_frequency(db, ['apName'], 'ClientCounts',fExcel, 'subkey = "All"')
        rfStat = check_frequency(db, ["apName", 'baseRadioMac', 'slotId'], 'RFStats', fExcel)
        clntSpec = check_frequency(db, ["apName"], 'ClientStats', fExcel)
        fExcel.save()

        rfCntS = set(rfCnt['apName'].tolist())
        clntTrS = set(clntTr['apName'].tolist())
        clntCtS = set(clntCt['apName'].tolist())
        rfStatS = set(rfStat['apName'].tolist())
        clntSpecS = set(clntSpec['apName'].tolist())


        goodApSet = set.intersection(rfCntS, clntTrS, clntCtS, rfStatS, clntSpecS)
        # print goodApSet

        apQueries = 'select apName, avg(count) as cnt, avg(authCount)  from ClientCounts  where subkey == "All" group by apName order by cnt DESC limit 200;'

        h, r = db.execute_query(apQueries)


        for apName, avgCount, avgAuthCount in r:
            if apName in goodApSet:
                selctedAp =  apName
                break
        print apName
        sys.exit(0)

    firstTs = datetime_to_epoch('8/18/2016')
    lastTs = datetime_to_epoch('8/23/2016')

    clientsDf, trafDf, joinedC, radioDf, radioStatsDf, countsDf = profile_specific_ap(db, selctedAp, firstTs, lastTs)

    joinedT =  pandas.concat([joinedC, radioDf, radioStatsDf, countsDf], axis=1)
    joinedT.sort_index(inplace = True)
    # joinedT.fillna(0, inplace = True)
    # joinedT =  pandas.concat([joinedC])

    outExcel = pandas.ExcelWriter(selctedAp + '.xlsx',
        datetime_format='yyyy-mm-dd hh:mm:ss')

    radioDf.to_excel(outExcel,'RF counters')
    radioStatsDf.to_excel(outExcel,'RF stats')
    clientsDf.to_excel(outExcel,'Client counters')
    trafDf.to_excel(outExcel,'Traffic counters')
    joinedC.to_excel(outExcel,'Client stats')
    joinedT.to_excel(outExcel,'All stats')
    outExcel.save()
    # joined.plot(style='o')
    # joinedT.plot(colormap='cubehelix')
    # plt.show()

