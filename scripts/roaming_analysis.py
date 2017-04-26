from post_process_data import *
import bisect

tsVector = None
apVector = None
apSet =None

def find_associated_ap(timestamp):
    index = bisect.bisect(tsVector, timestamp)
    if index == 0:
        return None
    else:
        return apVector[index]

def add_ap_indicator(inSeries):
    referenceVal = inSeries.max(skipna = True).max(skipna = True)
    for ap in apSet:
        inSeries[ap] = inSeries.apply(lambda x : referenceVal if find_associated_ap(datetime_to_epoch(x.name)) == ap else None, axis = 1)

def diff_with_roaming(db, keys, tableName):
    queryKeys = ','.join(keys)
    query = 'select timestamp, clientMac, apName, {0} from {1} order by timestamp;'.format(queryKeys, tableName)
    h, r = db.execute_query(query)
    df = create_pandas(r, h)

    df.reset_index(level=0, inplace=True)

    idG = df.groupby('clientMac')['apName'].transform(lambda x : (x.shift(1) != x).astype(int).cumsum())
    gg = pandas.concat([df,idG.to_frame('apSeq')],  axis=1)
    grouped = gg.groupby(['clientMac', 'apSeq'])
    avgG = grouped.mean()
    # avgG.columns = [k + '_avg' for k in keys]
    diff = avgG.diff()
    diff.columns = [k  for k in keys]
    # diff.rename('snr_diff')
    names = grouped['apName'].unique()
    return pandas.concat([names, diff],  axis=1)

def add_delta(x):
    x['delta'] =  x['associationTime']- x['timestamp'].shift(1)
    x['duration'] = x['timestamp']  - x['associationTime']
    return x

def association_times(db):
    query = 'select clientMac, apName, timestamp, snr, associationTime from ClientDetails order by associationTime;'
    h, r = db.execute_query(query)
    df = pandas.DataFrame(r, columns=h)
    lastTs = pandas.to_datetime('8/22/2016', utc = True)
    df = df[pandas.to_datetime(df['timestamp'], unit = 'ms', utc = True) < lastTs]
    groupedData = df.groupby(['clientMac', 'apName', 'associationTime'])
    aggF = { 'timestamp' : lambda x : x.max(),
            'snr' : lambda x : x.dropna().mean()
      }
    df = groupedData.agg(aggF)
    df = df.reset_index(inplace=False)
    df.loc[df['associationTime'] == 0, 'associationTime'] = df.loc[df['associationTime'] == 0, 'timestamp']
    df.sort(columns=['timestamp'], inplace=True )
    df = df.groupby(['clientMac']).apply( lambda xx: add_delta(xx))
    df = df.reset_index(inplace=False)
    return df


def histogram(values, outExcel, name):
    binNum = values.nunique()
    if binNum < 100:
        h = values.value_counts(bins = binNum)
    else:
        h = values.value_counts(bins =100)
    h = h.to_frame(name)
    h.sort_index(inplace = True)
    h.to_excel(outExcel, name)

def mean_of_positive(x, column):
    v = x[x > 0]
    v.dropna(inplace = True)
    return v.mean()


db = SqliteDb('/home/dipietro/arruzzolate/data_analysis_panda/example.db')

df = association_times(db)

# deltas = df.groupby(['clientMac']).transform(lambda x : x.loc['associationTime'] = x['associationTime']- x['timestamp'].shift(-1))

outExcel = pandas.ExcelWriter('roaming_transitions.xlsx')

grouped = df.groupby('clientMac')
# avgDuration = grouped['duration'].mean() / 60000.0
avgDuration = grouped.agg({'duration' : lambda x : mean_of_positive(x,'duration')})['duration'] / 60000
avgDuration = avgDuration[avgDuration < 3 * 24 * 60]
avgDelta = grouped.agg({'delta' : lambda x : mean_of_positive(x,'delta')})['delta'] / 60000
avgDelta = avgDelta[avgDelta < 60]

# avgDelta = grouped.agg({'delta' : lambda x : x.dropna().mean()/ 60000.0})['delta']
numTransitions = grouped['timestamp'].count()

histogram(avgDuration, outExcel, 'avgDuration')
histogram(avgDelta, outExcel, 'avgDelta')
histogram(numTransitions, outExcel, 'numTransitions')

outExcel.save()


# df = diff_with_roaming(db, ['snr', 'dataRate', 'dataRetries/(1.0 *packetsSent)', ], 'ClientStats')

# outExcel = pandas.ExcelWriter('roaming_transitions.xlsx')

# for name, values in df.iteritems():
#     if name == 'apName':
#         continue
#     name = name.replace('/','')
#     name = name.replace('*','x')
#     binNum = values.nunique()
#     if binNum == 1:
#         h = values.value_counts()
#     else:
#         h = values.value_counts(bins =100)
#     h = h.to_frame(name)
#     h.sort_index(inplace = True)
#     h.to_excel(outExcel, name)

# outExcel.save()

# query = 'select clientMac, count (distinct apName) as cnt from ClientDetails group by clientMac order by cnt desc limit 10;'

# # select * from ClientDetails where clientMac = "a4:70:d6:84:d9:15"

# h, r = db.execute_query(query)

# selectedApMac = r[0][0]

# query = 'select apName, timestamp  from ClientDetails where clientMac == "{}" order by timestamp;'.format(selectedApMac)

# h, r = db.execute_query(query)
# clntDetails = create_pandas(r, h)
# # print clntDetails

# tsVector = [rr[1] for rr in r]
# apVector = [rr[0] for rr in r]
# apSet = set(apVector)

# pastAp, pastTs = r.pop(10)

# clientsDfPast = pandas.DataFrame()
# trafDfPast = pandas.DataFrame()
# joinedCPast = pandas.DataFrame()
# radioDfPast = pandas.DataFrame()
# radioStatsDfPast = pandas.DataFrame()
# countsDfPast = pandas.DataFrame()

# cnt = 0
# for ap, ts in r:
#     if ap == pastAp:
#         continue
#     cnt += 1
#     if cnt == 5:
#         break
#     firstTs = pastTs
#     lastTs = ts
#     print ap + ':' + str(pandas.to_datetime(firstTs, unit = 'ms', utc = True)) + ' -> ' +  str(pandas.to_datetime(lastTs, unit = 'ms', utc = True))
#     clientsDf, trafDf, joinedC, radioDf, radioStatsDf, countsDf = profile_specific_ap(db, pastAp, firstTs, lastTs)
#     pastAp = ap
#     pastTs = ts
#     # print clientsDf
#     clientsDfPast = pandas.concat([clientsDfPast, clientsDf])
#     trafDfPast = pandas.concat([trafDfPast, trafDf])
#     joinedCPast = pandas.concat([joinedCPast, joinedC])
#     radioDfPast = pandas.concat([radioDfPast, radioDf])
#     radioStatsDfPast = pandas.concat([radioStatsDfPast, radioStatsDf])
#     countsDfPast = pandas.concat([countsDfPast, countsDf])


# outExcel = pandas.ExcelWriter(selectedApMac + '.xlsx',
#     datetime_format='yyyy-mm-dd hh:mm:ss')

# add_ap_indicator(radioDfPast)
# radioDfPast.to_excel(outExcel,'RF counters')
# add_ap_indicator(radioStatsDfPast)
# radioStatsDfPast.to_excel(outExcel,'RF stats')

# clientsDfPast = clientsDfPast[clientsDfPast['macAddress'] == selectedApMac]

# # query = 'select *  from ClientStats where macAddress == "{}" order by timestamp;'.format(selectedApMac)

# # h, r = db.execute_query(query)

# # rawClnts = create_pandas(r, h)

# # rawClnts.to_excel(outExcel,'Mac counters')
# add_ap_indicator(clientsDfPast)
# clientsDfPast.to_excel(outExcel,'Client counters')

# # add_ap_indicator(trafDfPast)
# # trafDfPast.to_excel(outExcel,'Traffic counters')

# add_ap_indicator(joinedCPast)
# joinedCPast.to_excel(outExcel,'Client stats')


# # print clientsDfPast
# # print trafDfPast
# # print joinedCPast
# # print radioDfPast
# # print radioStatsDfPast
# # print countsDfPast
# joinedTPast =  pandas.concat([joinedCPast, radioDfPast, radioStatsDfPast, trafDfPast], axis=1)
# joinedTPast.sort_index(inplace = True)
# # print joinedTPast
# add_ap_indicator(joinedTPast)
# joinedTPast.to_excel(outExcel,'All stats')
# outExcel.save()