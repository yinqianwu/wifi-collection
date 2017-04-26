import sys
import os
import time
import logging
import subprocess
import json
import datetime
import yaml
import threading
import signal
import argparse

import commonlib.sln_params_parsing as sln_params_parsing

from commonlib.sln_connections import *
from commonlib.sln_logging import SlnLogging


class DetachedExec:

    """ Creation and termination of thread is handled in this class"""

    def __init__(self, functor, name, *argv):
        """Initializes the thread functor and starts a thread"""
        #log.debug('Executing DetachedExec.__init__ for %s'  %name)
        self.functor = functor
        self.thread = threading.Thread(target=functor, args=argv)

        self.name = name
        self.thread.setDaemon(True)
        self.thread.start()

    def terminate_in_max(self, timeoutSecs):
        """Terminates the thread after waiting number of seconds provided as an argument"""
        #log.debug('Executing DetachedExec.terminate_in_max: %s ' %self.name)
        self.thread.join(timeoutSecs)
        self.kill_thread()

    def kill_thread(self):
        """Terminates the thread"""
        if (self.thread.isAlive()):
            # self.thread._Thread__delete()
            if hasattr(self.functor, 'request_terminate'):
                self.functor.request_terminate()

    def join_thread(self, timeout=None):
        """Waits for the thread to finish"""
        # log.debug('Executing DetachedExec.join_thread %s ' %self.name)
        if(self.thread.isAlive()):
            if(timeout == None):
                self.thread.join()
            else:
                #log.debug('Waiting for the %s. thread to join %s seconds' %(self.name, str(timeout)))
                self.thread.join(timeout)

    def isAlive(self):
        """ Returns the status of the thread"""
        return self.thread.isAlive()

    def __del__(self):
        #log.debug('Executing DetachedExec.__del__: Thread Name: %s' %self.name)
        #log.debug ('DetachedExec: killing %s' %(repr(self.functor)))
        self.kill_thread()


def epoch_to_std_time(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def query_str_since(epoch):
    return 'gt("{0}")'.format(epoch_to_std_time(epoch))


def query_str_between(firstEpoch, lastEpoch):
    return 'between("{0}","{1}")'.format(epoch_to_std_time(firstEpoch), epoch_to_std_time(lastEpoch))


def query_str_between_epoch(firstEpoch, lastEpoch):
    return 'between("{0}","{1}")'.format(int(firstEpoch) * 1000, int(lastEpoch) * 1000)


def time_filtering_map(fieldName, firstEpoch, lastEpoch=None):
    firstEpochStr = int(firstEpoch) * 1000
    retMap = {}
    if lastEpoch is None:
        retMap[fieldName] = 'gt("{0}")'.format(firstEpochStr)
    else:
        lastEpochStr = int(lastEpoch) * 1000
        retMap[fieldName] = 'between("{0}","{1}")'.format(
            firstEpochStr, lastEpochStr)
    return retMap


class Datapoller:

    def __init__(self, api, outDir, path, tsField, pollingInterval, pollingWindow, maxFileSize, logger, furtherFiltering={}):
        self.nextPollingTs = time.time()
        # self.pollingInterval = pollingWindow / 3
        self.pollingInterval = pollingInterval
        self.pollingWindow = pollingWindow
        self.api = api
        self.path = path
        self.sentEventsSet = set([])
        self.sentEventsList = []
        self.tsField = tsField
        self.furtherFiltering = furtherFiltering
        self.itemType = [p for p in path.split('/') if len(p) > 0][-1]
        self.outDir = outDir
        self.openFileName = self.get_filename()
        self.fd = open(self.openFileName, 'w')
        self.maxFileSize = maxFileSize
        self.logger = logger

    def get_keys_for(self, paging=500,  maxRes=None, filteringMap={}):
        basePath = self.path.rstrip('/').lstrip('/')
        basePath = '/' + basePath
        baseQuery = basePath + '.json'
        # baseQuery = basePath
        outResults = []

        # Initially, assume there may be a large number of
        # records to retrieve
        entityCount = sys.maxsize
        firstResult = 0

        global threadsRunning
        while threadsRunning and firstResult < entityCount:
            params = {
                '.full': 'true',
                '.firstResult': firstResult,
                '.maxResults': paging
            }

            params.update(filteringMap)
            retObj = self.api.get_objk(baseQuery, params=params)

            if retObj is None:
                self.logger.debug('retObj is none')
                continue

            self.logger.info(
                "Response to "
                + retObj['queryResponse']["@requestUrl"]
                + " with entityCount: {0}, firstResult: {1}".format(
                    entityCount,
                    firstResult
                ))

            # Make sure that for these filters, @count does not change
            atCount = int(retObj['queryResponse']['@count'])

            if entityCount == sys.maxsize:
                entityCount = atCount
            elif entityCount != atCount:
                self.logger.error(
                    "Entity count has changed from "
                    "{0} to {1}, firstResult: {2}".format(
                        entityCount,
                        atCount,
                        firstResult
                    ))

                # Abort fetching results for this key. Maybe we even want
                # to return an empty set of results?
                break

            if entityCount == 0:
                self.logger.info(
                    "@count is 0, entityCount: {0}, firstResult: {1}".format(
                        entityCount,
                        firstResult
                    ))
                break

            # Since @count is nonzero and we're trying to page in a smart way
            # there should always be entities returned
            if 'entity' not in retObj['queryResponse'].keys():
                self.logger.error(
                    "No entities, entityCount: {0}, firstResult: {1}".format(
                        entityCount,
                        firstResult
                    ))

                self.logger.error(json.dumps(retObj, indent=2))

                # This is not expected, abort
                break

            lastIndex = int(retObj['queryResponse']['@last'])
            firstIndex = int(retObj['queryResponse']['@first'])

            returnedEntities = len(retObj['queryResponse']['entity'])
            expectedEntities = lastIndex - firstIndex + 1

            if returnedEntities != expectedEntities:
                self.logger.error(
                    "Expected {0} entities, got {1}".format(
                        expectedEntities,
                        returnedEntities
                    ))

                # This is not expected, abort
                break

            # Move the page to get the next elements
            firstResult = lastIndex + 1
            outResults += retObj['queryResponse']['entity']

            if (maxRes is not None) and (len(outResults) > maxRes):
                self.logger.debug('max res reached')
                break

        if entityCount != firstResult:
            self.logger.error(
                "Pager exited with entityCount: {0}, firstResult: {1}".format(
                    entityCount,
                    firstResult
                ))
        try:
            # Debugging for the clients counts endpoint
            collectionTimes = [
                int(x['clientCountsDTO']['collectionTime']) for x in outResults]
            minCollTimeSecs = min(collectionTimes) / 1000
            maxCollTimeSecs = max(collectionTimes) / 1000

            self.logger.info(
                "Events: collectionTime ranging from {0} to {1}".format(
                    datetime.datetime.fromtimestamp(
                        minCollTimeSecs
                    ).strftime('%Y-%m-%d %H:%M:%S.%f'),
                    datetime.datetime.fromtimestamp(
                        maxCollTimeSecs
                    ).strftime('%Y-%m-%d %H:%M:%S.%f'),
                ))
        except:
            pass

        self.logger.debug(basePath + ':Read ' + str(len(outResults)))

        return outResults

    def get_filename(self):
        return (
            self.outDir
            + '/' + self.itemType + '_' + str(int(time.time())) + '.json'
        )

    def rotate_file(self):
        self.fd.flush()
        size = os.fstat(self.fd.fileno()).st_size
        if size > self.maxFileSize:
            self.fd.close()
            self.openFileName = self.get_filename()
            self.fd = open(self.openFileName, 'w')

    def process_data_type(self):
        ts = time.time()
        if (ts < self.nextPollingTs):
            return

        filteringMap = self.furtherFiltering
        if self.tsField is not None:
            filteringMap.update(
                time_filtering_map(self.tsField, time.time() - self.pollingWindow))

        objs = self.get_keys_for(maxRes=None, filteringMap=filteringMap)
        # print (keys)
        totObjReturned = len(objs)

        self.rotate_file()

        numSkipped = 0
        numDumped = 0

        for o in objs:
            itemType = o["@dtoType"]
            data = o[itemType]
            itemId = int(data['@id'])
            if itemId in self.sentEventsSet:
                self.logger.debug(
                    '{0}: skipping {1}'.format(self.itemType, itemId))
                numSkipped += 1
                continue
            ts = int(time.time())
            collectionTsMs = int(ts * 1000)

            numDumped += 1
            self.sentEventsSet.update([itemId])
            self.sentEventsList.append((itemId, ts))

            if self.tsField is not None:
                timestampMs = int(data[self.tsField])
            else:
                timestampMs = collectionTsMs
            data['$timestamp'] = timestampMs
            data['$local_timestamp'] = collectionTsMs

            self.fd.write(json.dumps(data) + '\n')
            self.fd.flush()
        self.logger.info(
            "{0}: Skipped a total of {1}".format(self.itemType, numSkipped))
        self.logger.info("{2}: Dumped a total of {0} over {1}".format(
            numDumped, totObjReturned, self.itemType))

        tsToErase = int(time.time()) - self.pollingWindow

        numErased = 0
        latestErased = 0
        while ((len(self.sentEventsList) > 0) and (self.sentEventsList[0][1] < tsToErase)):
            latestErased = max(latestErased, self.sentEventsList[0][1])
            numErased += 1
            self.sentEventsSet.remove(self.sentEventsList[0][0])
            self.sentEventsList.pop(0)
        ts = time.time()
        self.logger.info('{0}: Erased {1} events. Latest was {2} min. ago'.format(
            self.itemType, numErased, (ts - latestErased) / 60))
        self.logger.debug(
            '{0} : pending events {1}'.format(self.itemType, len(self.sentEventsSet)))
        self.nextPollingTs = ts + self.pollingInterval


threadsRunning = True


class ServerPoller:

    def __init__(self, generalParams, serverDesc, dataDesc, commitHash, maxNumPolls):
        self.maxNumPolls = maxNumPolls

        logDir = generalParams['log_directory']
        maxFileSize = generalParams['data_file_rotation_thr']
        self.sleepTime = serverDesc["check_interval"]

        dataPrefix = serverDesc['data_prefix']
        if dataPrefix is None:
            dataPrefix = serverDesc['ip']

        outDir = os.path.join(generalParams['data_directory'], dataPrefix)
        if not os.path.isdir(outDir):
            os.makedirs(outDir)

        metadataFile = os.path.join(outDir, 'metadata_' + str(int(time.time())) + '.json')

        metadata = {}

        metadata['commit_hash'] = commitHash
        metadata['polled_server'] = serverDesc['ip']
        metadata['polled_data'] = dataDesc

        mfh = open(metadataFile, 'w')

        mfh.write(json.dumps(metadata, indent=2))

        mfh.close()

        log = SlnLogging.get_sln_logger('rest_' + dataPrefix, logging.INFO)

        if logDir:
            lofFileName = os.path.join(logDir, 'prime_' + dataPrefix + '.log')
            logFd = open(lofFileName, 'w')
            SlnLogging.set_file_handler(log, logFd)

        self.dataPollers = []

        for d in dataDesc:
            # TODO: make this cleaner. According to the doc,
            # this endpoint should NOT be queried with v1.
            if "ClientDetails" in d["api_path"]:
                api_version = "v2"
            else:
                api_version = serverDesc['api_version']

            argMap = {'ip': serverDesc['ip'],
                  'basePath': serverDesc['base_path'],
                  'username': serverDesc['username'],
                  'password': serverDesc['password'],
                  'tokenUserName': None,
                  'tokenPassword': None,
                  'port': serverDesc['port'],
                  'api_version': api_version,
                  'thread_log': log}

            argMap = {
                'api': RestApi(**argMap),
                'outDir': outDir,
                'path': d["api_path"],
                'tsField': d["timestamp_field"],
                'pollingInterval': d["check_interval"],
                'pollingWindow': d["check_window"],
                'maxFileSize': maxFileSize,
                'logger': log,
                'furtherFiltering': {'status': 'ASSOCIATED'} if d["only_associated"] else {}
            }

            self.dataPollers.append(Datapoller(**argMap))

    def __call__(self):
        poll_num = 0

        global threadsRunning
        while threadsRunning:
            for poller in self.dataPollers:
                if not threadsRunning:
                    return
                poller.process_data_type()

            log.info("Waiting for next poll")
            poll_num += 1

            if (self.maxNumPolls is not None) and (poll_num >= self.maxNumPolls):
                return

            time.sleep(self.sleepTime)


def _get_arg_parser():
    parser = argparse.ArgumentParser(add_help=True)

    parser.add_argument("--max-num-polls",
                        default=None,
                        type=int,
                        help="Maximum number of poll rounds to perform")

    parser.add_argument("--log-directory",
                        default=None,
                        help="Override YAML configuration")

    parser.add_argument("--log-stdout",
                        action="store_true")

    parser.add_argument("--data-directory",
                        default=None,
                        help="Override YAML configuration")

    parser.add_argument("--file-rotation-thr",
                        default=None,
                        type=int,
                        help="Override YAML configuration")

    parser.add_argument("--git-commit-hash",
                        default="",
                        help="Git commit hash -- auto-detected if omitted and GIT_COMMIT_HASH undefined")

    parser.add_argument("config",
                        help="Configuration file",
                        default="")

    return parser


def signal_handler(signal, frame):
    global threadsRunning
    threadsRunning = False

    # Wait a little bit, and exit without failure code
    time.sleep(70)
    sys.exit(0)


def _override_args(args, generalConfig):
    if args.log_directory is not None:
        generalConfig['log_directory'] = args.log_directory

    if args.data_directory is not None:
        generalConfig['data_directory'] = args.data_directory

    if args.file_rotation_thr is not None:
        generalConfig['file_rotation_thr'] = args.file_rotation_thr

    return generalConfig

if __name__ == '__main__':
    parser = _get_arg_parser()
    args = parser.parse_args()

    if args.log_stdout:
        logging.basicConfig(level=logging.INFO)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        config_fd = open(args.config)
    except IOError as err:
        log.error("Unable to open config YAML file. {}".format(err))
        sys.exit(1)

    inputParameters = yaml.load(config_fd)

    generalParamsParser = sln_params_parsing.ParamsMap(
        descriptionMap=sln_params_parsing.generalArgs,
        defaultValues={},
        loggingString='general')

    generalConfig = _override_args(
        args,
        generalParamsParser.read_input_values(inputParameters['general_configs']))

    dataPollers = []

    for i, dataConfig in enumerate(inputParameters['data_to_be_polled']):
        dataDescParser = sln_params_parsing.ParamsMap(
            descriptionMap=sln_params_parsing.dataListArgs,
            defaultValues={},
            loggingString='data_' + str(i))
        dataDesc = dataDescParser.read_input_values(dataConfig)
        dataPollers.append(dataDesc)

    serverConfigs = []

    for i, serverConfig in enumerate(inputParameters['prime_servers']):
        serverConfParser = sln_params_parsing.ParamsMap(
            descriptionMap=sln_params_parsing.serverArgs,
            defaultValues={},
            loggingString='server_' + str(i))
        serverDesc = serverConfParser.read_input_values(serverConfig)
        serverConfigs.append(serverDesc)

    if args.git_commit_hash:
        commitHash = args.git_commit_hash
    elif "GIT_COMMIT_HASH" in os.environ and os.environ["GIT_COMMIT_HASH"]:
        commitHash = os.environ["GIT_COMMIT_HASH"]
    else:
        commitHash = subprocess.check_output('git rev-parse  HEAD', shell=True)
        commitHash = commitHash.decode("utf-8")
        commitHash = commitHash.rstrip('\n')

    log.info("Commit hash: {0}".format(commitHash))

    threadObjs = []

    for i, s in enumerate(serverConfigs):
        obj = ServerPoller(
            generalConfig, s, dataPollers, commitHash, args.max_num_polls)
        threadObjs.append(DetachedExec(obj, 'poller_' + str(i)))

    numThreads = len(threadObjs)

    while True:
        numThreadTerminated = 0
        for obj in threadObjs:
            obj.join_thread(1)
            if not obj.isAlive():
                numThreadTerminated += 1
        if (numThreadTerminated == numThreads):
            break
        time.sleep(1)
