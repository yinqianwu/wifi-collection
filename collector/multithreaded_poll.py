import threading
import queue
import json
from  commonlib.sln_connections import *


class DetachedExec:
    ''' Creation and termination of thread is handled in this class'''
    def __init__(self, functor, name, *argv):
        '''Initializes the thread functor and starts a thread'''
        #log.debug('Executing DetachedExec.__init__ for %s'  %name)
        self.functor = functor
        self.thread = threading.Thread(target=functor, args=argv)

        self.name  = name
        self.thread.setDaemon(True)
        log.debug('Before Start Thread %s :  %s ' %(name ,str(functor)))
        self.thread.start()

    def terminate_in_max(self, timeoutSecs):
        '''Terminates the thread after waiting number of seconds provided as an argument'''
        #log.debug('Executing DetachedExec.terminate_in_max: %s ' %self.name)
        self.thread.join(timeoutSecs)
        self.kill_thread()

    def kill_thread(self):
        '''Terminates the thread'''
        log.debug('Executing DetachedExec.kill_thread %s' %self.name)
        if (self.thread.isAlive()):
            # self.thread._Thread__delete()
            if hasattr(self.functor,'request_terminate'):
                self.functor.request_terminate()

    def join_thread(self, timeout = None):
        '''Waits for the thread to finish'''
        # log.debug('Executing DetachedExec.join_thread %s ' %self.name)
        if(self.thread.isAlive()):
            if(timeout == None):
                self.thread.join()
                log.debug('Executed DetachedExec.join_thread %s  returned' %self.name)
            else:
                #log.debug('Waiting for the %s. thread to join %s seconds' %(self.name, str(timeout)))
                self.thread.join(timeout)

    def isAlive(self):
        ''' Returns the status of the thread'''
        return self.thread.isAlive()

    def __del__(self):
        #log.debug('Executing DetachedExec.__del__: Thread Name: %s' %self.name)
        #log.debug ('DetachedExec: killing %s' %(repr(self.functor)))
        self.kill_thread()

requestsQueue = queue.Queue()

dataQueue = queue.Queue()

threadsVec = []

terminateRequest = False


def process_from_queue(apiObj):
    curItem = None
    numRetries = 0
    maxRetries = 3
    log = apiObj.log
    while not terminateRequest:
        if curItem is None:
            item = requestsQueue.get()
            requestsQueue.task_done()
        else:
            log.debug('retrying')
            item = curItem
        itemType, itemId = item

        itemName =  itemType + '/' + str(itemId)
        log.debug('processing ' + itemName)

        itemType = itemType.rstrip('/').lstrip('/')
        urlObj = '/' + itemType + '/' + str(itemId) + '.json'
        res = apiObj.get_objk(urlObj)
        if res is None:
            curItem = item
            numRetries += 1
            if (numRetries >= maxRetries):
                curItem = None
                numRetries = 0
                log.error('Giving up on querying ' + itemName)
            else:
                log.debug('scheduling for reprocessing ' + itemName)
            continue
        else:
            curItem = None
        log.info('requests queue length ' + str(requestsQueue.qsize()))
        dataQueue.put(res)

def dump_results(outDir):
    fdMap = {}
    while not terminateRequest:
        item = dataQueue.get()
        itemType = item["queryResponse"]["@type"]
        if itemType not in fdMap.keys():
            fd = open(outDir + '/' + itemType + '.json', 'w')
            fdMap[itemType] = fd
        fd = fdMap[itemType]
        dataQueue.task_done()
        fd.write(json.dumps(item) + '\n')
        fd.flush()
        log.info('data queue length ' + str(dataQueue.qsize()))
    fd.close()


def start_consumer_threads(apiObjParams, numThreads, outFile):

    for n in range(0, numThreads):
        objCopy = RestApi(**apiObjParams)
        t = DetachedExec(process_from_queue, 'reader_' + str(n), objCopy)
        threadsVec.append(t)
    t = DetachedExec(dump_results, 'consumer', outFile)
    threadsVec.append(t)


def enqueue_data(itemType, itemId):
    requestsQueue.put((itemType, itemId))


def stop_threads():
    terminateRequest = True
    num_of_dlas = len(threadsVec)
    while(True):
        num_dla_terminated = 0
        for obj in threadsVec:
            #write_results(results_file, results_info):
            obj.join_thread(1)
            if not obj.isAlive():
                num_dla_terminated += 1
        if (num_dla_terminated == num_of_dlas):
            break
        time.sleep(1)