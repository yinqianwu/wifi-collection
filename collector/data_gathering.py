import json
from cli_parsing_utils import *


class StatsGathering:
    def __init__(self, connection, evLog, cliLog = None):
        self.connection = connection
        self.evLog = evLog
        self.cliLog = cliLog if cliLog is not None else evLog

    def index_summary(self, cmd, index):
        try:
            summaryStr = self.connection.execute(cmd, cmdLog = self.cliLog).split('\n')
        except Exception as e:
            self.evLog.error('CLI execution error ' + str(e))
            return {}

        try:
            sumMaps = parse_summary_maps(summaryStr)
        except Exception as e:
            self.evLog.error('Sumamry parsing error ' + str(e) + '\n while parsing: \n' + str(summaryStr))
            return {}

        if (len(sumMaps) == 0):
            return {}
        targetMaps =  [m for m in sumMaps if index in m.keys()]
        if len(targetMaps) != 1:
            self.evLog.error('Wrong number of maps ' + str(len(targetMaps)))
            return {}
        try:
            retMap = indexed_results_map(targetMaps[0], index)
        except Exception as e:
            self.evLog.error('Sumamry indexing error ' + str(e) + '\n while parsing: \n' + str(targetMaps[0]))
            return {}
        return retMap

    def details_map(self, cmd):
        try:
            rawStr = self.connection.execute(cmd, cmdLog = self.cliLog).split('\n')
        except Exception as e:
            self.evLog.error('CLI execution error ' + str(e))
            return {}
        #skip show command line
        try:
            sumMaps = parse_details(rawStr[1:])
        except Exception as e:
            self.evLog.error('details error ' + str(e) + '\n while parsing: \n' + str(rawStr))
            return {}
        return sumMaps



    def client_info(self):
        clMap = self.index_summary( 'show client summary', 'MAC Address')
        for c in clMap.keys():
            details = self.details_map( 'show client detail ' + c)
            clMap[c]['details'] = details
        return clMap


    def rogue_info(self):
        rogueClientsMap = self.index_summary( 'show rogue client summary', 'MAC Address')
        for c in rogueClientsMap.keys():
            details = self.details_map( 'show rogue client detailed ' + c)
            rogueClientsMap[c]['details'] = details
        rogueApMap = self.index_summary( 'show rogue ap summary', 'MAC Address')
        for c in rogueApMap.keys():
            details = self.details_map( 'show rogue ap detailed ' + c)
            rogueApMap[c]['details'] = details
        return (rogueClientsMap, rogueApMap)


    def ap_info(self):
        allApInfo = self.index_summary( 'show ap summary', 'AP Name')
        retMap = {}
        for apName, apInfo in allApInfo.items():
            apMap = {'general': apInfo}
            radioList = ['802.11a', '802.11b']
            # show ap config 802.11a AP2
            apMap ['ap_config'] = {}
            cmd = 'show ap config {0} {1}'
            extRadioList = radioList + ['general']
            for radio in extRadioList:
                details = self.details_map( cmd.format(radio, apName))
                apMap['ap_config'][radio] = details

            details = self.details_map( 'show ap channel {0}'.format(apName))
            apMap ['ap_channel'] = details

            apMap['ap_stats'] = {}
            cmd ='show ap stats {0} {1}'
            for radio in radioList:
                details = self.details_map( cmd.format(radio, apName))
                apMap['ap_stats'][radio] = details

            cmd ='show ap auto-rf {0} {1}'
            apMap['ap_auto_rf'] = {}
            for radio in radioList:
                details = self.details_map( cmd.format(radio, apName))
                apMap['ap_auto_rf'][radio] = details
            retMap[apName] = apMap
        return retMap


    def radius_info(self):
        retMap = {}
        retMap['auth'] = self.details_map('show radius auth statistics')
        retMap['acc'] = self.details_map('show radius acct statistics')
        return retMap



    def dhcp_info(self):
        return self.details_map('show dhcp stats')


    def gather_data(self):
        retMap = {}
        apInfo = self.ap_info()
        clntMap = self.client_info()
        rogueClientsMap, rogueApMap = self.rogue_info()
        retMap['ap_stats'] = apInfo
        retMap['rogue_aps_stats'] = rogueApMap
        retMap['rogue_clnt_stats'] = rogueClientsMap
        retMap['clnt_stats'] = clntMap
        retMap['radius_stats'] = self.radius_info()
        retMap['dhcp_stats'] = self.dhcp_info()

        return retMap

        # print (json.dumps(clntMap, indent = 2))
        # print (json.dumps(rogueClientsMap, indent = 2))
        # print (json.dumps(rogueApMap, indent = 2))
        # print (json.dumps(apInfo, indent = 2))

