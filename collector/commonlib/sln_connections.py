#
# SLN Connection Mgmt for install/upgrade automation
#                                                                                 #
# Copyright (c) 2016 by cisco Systems, Inc.
# All rights reserved. This program contains proprietary
# and confidential information.
#--------------------------------------------------------------
#
import sys
import time
import json
import requests
import re
import pexpect
import socket
import logging
import pexpect.pxssh as pxssh
from commonlib.sln_logging import SlnLogging
from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

log = SlnLogging.get_sln_logger("main", logging.DEBUG)


class SSHRemoteClient_pexpect(object):
    ''' Class SSHRemoteClient_pexpect: creates a ssh channel to a remote machine and allows communication over this channel'''
    def __init__(self, hostname, username, password='', port=22, thread_log = None, inter_cli_time = None):
        # print (thread_log)
        if thread_log == None:
            self.log = log
        else:
            self.log = thread_log

        self.log.debug('Executing SSHRemoteClient_pexpect.__init__')
        self.username = username
        self.password = password
        self.hostname = hostname
        self.port = port
        self.mainChannel = pxssh.pxssh(
            # options={
            #     "StrictHostKeyChecking": "no",
            #     "UserKnownHostsFile": "/dev/null"}
            )
        self.inter_cli_time =  inter_cli_time
        self.iosErrorRegexps = ( re.compile('(?i)(?<=\n)% *(:error|invalid|unknown|[\d.]+ *overlaps with).*(?=\r\n)'), )

    def check_ios_error_messages(self):
        retStr = self.mainChannel.before.decode()
        for errDel in self.iosErrorRegexps:
            errmatch = errDel.search(retStr)
            if not errmatch:
                continue
            return errmatch.group(0)
        return None

    def set_prompt(self):
        '''
        Sets the router prompt on which pexpect waits after execution of command
        '''
        self.log.debug('Executing SSHRemoteClient_pexpect.set_prompt')
        self.mainChannel.sendline()
        time.sleep(0.1)
        prompt_1 = self.mainChannel.try_read_prompt(2)
        prompt_1 = prompt_1.decode('ascii')
        # print (repr(prompt_1))
        # prompt_1 = '\r\n' + prompt_1.split('\n')[-1]
        # print (repr(prompt_1))
        self.mainChannel.sendline()
        time.sleep(0.1)
        prompt_2 = self.mainChannel.try_read_prompt(2)
        prompt_2 = prompt_2.decode('ascii')
        # print (repr(prompt_2))
        # prompt_2 = '\r\n' + prompt_2.split('\n')[-1]
        # print (repr(prompt_2))

        if prompt_1 == prompt_2:
            self.mainChannel.PROMPT = prompt_1
        else:
            self.mainChannel.PROMPT = '[(.+)#]'
        self.mainChannel.PROMPT = prompt_2


        self.prompt = self.mainChannel.PROMPT
        self.log.debug('Prompt ' + repr(self.prompt))
        #workaround for detecting that the connection has actually been established
        failed = (len(prompt_1.replace('\n', '').replace('\r', '')) == 0) and \
                 (len(prompt_2.replace('\n', '').replace('\r', '')) == 0)
        return not failed

    def login(self, unix=False):
        ''' create_channel: Creates a ssh channel to a remote machine with the credentials provided'''
        try:
            self.log.debug('Executing SSHRemoteClient_pexpect.create_channel')
            self.log.debug('SSHRemoteClient_pexpect: Creating Channel %s@%s:%s' %(self.username, self.hostname, self.port))
            # self.client.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
            is_success = self.mainChannel.login(server = self.hostname, username = self.username,
                                                password = self.password, port=self.port,
                                                auto_prompt_reset = (unix and True or False))
            self.log.debug('SSHRemoteClient_pexpect: return from create_channel %s@%s:%s' %(self.username, self.hostname, self.port))
            #warning -> this returns true even if the connection attempt timed out
            if is_success == False:
                log.error('Failed to connect %s@%s:%s' %(self.username, self.hostname, self.port))
                return False

            timeout = 10
            self.mainChannel.expect(['User:'], timeout)
            out = self.mainChannel.before.decode('ascii')
            self.mainChannel.sendline(self.username)
            self.mainChannel.expect(['Password:'], timeout)
            out = self.mainChannel.before.decode('ascii')
            self.mainChannel.sendline(self.password)
            # expectStr = '*' * len(self.password)
            self.mainChannel.expect(['[*]?'], timeout)
            out = self.mainChannel.before.decode('ascii')

            connected = self.set_prompt()
            if (not connected):
                self.log.error('No prompt response from %s@%s:%s. Is the host reacheable?' %(self.username, self.hostname, self.port))
                return False
            self.log.info('Connected to %s@%s:%s' %(self.username, self.hostname, self.port))
            return True

        except pxssh.ExceptionPxssh as e:
            self.log.error('Connection error occurred while connecting to %s:%s : %s' %(self.hostname, self.port, str(e)))
        except pexpect.exceptions.EOF:
            self.log.error('Failed to start ssh session to {}@{}:{}. Likely hostname '\
                           'unresolvable or connection refused.'.format(self.username, self.hostname, self.port))
        return False


    def execute(self, command, timeout = 5, cmdLog = None):
        '''
        Executes the command and returns the output
        '''
        if (cmdLog is None):
            log =  self.log
        else:
            log =  cmdLog

        log.debug('Executing -----------------------------------\n%s\n--------------' %command)

        outBuf = self._execute(command, timeout)
        leftoverBuf = self._execute('', timeout)
        #make sure there is no leftover output
        while (len(leftoverBuf) > 0):
            outBuf += leftoverBuf
            leftoverBuf = self._execute('', timeout)

        log.debug('Output ---------------------------------------\n%s\n' % outBuf)
        log.debug('End of Output ---------------------------------------\n')
        if self.inter_cli_time is not None:
            time.sleep(self.inter_cli_time)
        return outBuf


    def _execute(self, command, timeout):


        self.mainChannel.sendline(command)
        try:
            index = self.mainChannel.expect_exact([self.prompt], timeout)

            errorMsg = self.check_ios_error_messages()
            if errorMsg is not None:
                self.log.error('Error while executing: %s', command)
                errStr = errorMsg.replace('\r','')
                self.log.error('Received error: %s', errStr)
                raise Exception(errStr)
        except pexpect.TIMEOUT:
           self.log.error('Time out while waiting for command(%s) to finish' %command)
           raise
        except pexpect.EOF:
           self.log.error('EOF exception while waiting for command(%s) to finish' %command)
           raise

        output = self.mainChannel.before.decode('ascii')

        return output

    def config(self,command,timeout=5):
        '''
        Execute the config command in config mode
        '''
        command = command.replace('\r','')
        command = 'config\n' + command + '\n end'

        output = self.execute(command, timeout)
        return output


    def closeConnection(self):
        self.log.debug('Executing SSHRemoteClient_pexpect.closeConnection')
        self.mainChannel.sendline('logout')
        self.mainChannel.close()





class RestApi:
    ''' Interacts with SCA REST API
        ARGS:
            ip: sca ip
            port: SCA REST port, usually 7070
            Username:
            Password:
            objectName: object name in REST e.g. '/dla', see Swagger UI in any browser at ip:port
    '''
    def __init__(self,
                 ip,
                 port=None,
                 username = None,
                 password = None,
                 tokenUserName = None,
                 tokenPassword = None,
                 api_version = 'v1',thread_log=None, basePath = ''):
        ''' Create a connection with the ip and port provided '''
        if thread_log == None:
            self.log = log
        else:
            self.log = thread_log
        self.log.debug('Executing RestApi.__init__')
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.connection_url = None
        #self.connection = http.client.HTTPConnection(ip, port)
        self.exception  = None
        self.running = False
        self.total_stat_calls = 0    # number of times the stats is called in __call__ function
        self.success_stat_calls = 0  # Count of Successfull attempts to fetch dla stats
        self.tokenUserName =  tokenUserName
        self.tokenPassword = tokenPassword
        assert((tokenUserName is None) == (tokenPassword is None))
        self.token = None
        self.version = api_version
        self.basePath =  basePath.rstrip('/').lstrip('/')

    def _set_connection_type(self, generateToken = True):
        '''
        _set_connection_type
        Description:
            Verifies the type of connection to SCA, e.g: http or https
        args:

        '''
        connection_url_base = self.ip
        if self.port is not None:
            connection_url_base += ':' + str(self.port)
        #self.connection_url = None
        if self.username is not None:
            self.connection_url = 'https://' + connection_url_base
        else:
            self.connection_url = 'http://' + connection_url_base
        baseStr = '/' +  self.basePath if self.basePath != '' else ''
        self.connection_url = self.connection_url + baseStr + '/' + self.version
        if (generateToken == True and self.tokenUserName is not None):
            ret = self._perform_post('/auth/login',  jsonStruct = {'user': self.tokenUserName, 'password': self.tokenPassword}, params=None)
            assert(ret is not None)
            self.token = ret["token"]

        self.log.info('REST API connection URL: %s' %self.connection_url)

    def log_out(self):
        '''
        Description:
            performs log out, which invalidates teh current key
        '''
        self.log.info('Logging out from sca and destroying the current key')
        if (self.token is not None):
            ret = self.get_objk('/auth/logout')
            assert(ret is not None)
        return True

    def change_admin_password(self, username,password,newPassword):
        '''
          Updates the current 'admin' user password.
        '''
        self.log.info('Changing admin user password.')
        self._set_connection_type(generateToken = False)
        url = '/auth/changepassword'
        data = {'user':username,'password':password ,'newPassword':newPassword}
        response = self.perform_post(url,data)
        assert(response is not None)
        self.tokenUserName =  username
        self.tokenPassword = newPassword
        ret = self._perform_post('/auth/login',  jsonStruct = {'user': self.tokenUserName, 'password': self.tokenPassword}, params=None)
        assert(ret is not None)
        self.token = ret["token"]

        self.log.info('Successfully updated the SCA "admin" user password')
        self.log.debug('Response:%s' %response)

    def generate_token(self, token_user, token_password):
        '''
        Description:
            Generates token, which is required to access REST API exposed by SCA
        args:
           token_user : username required to genraete the token
           token_password : password required to generate the token
        '''
        ## Not required for now
        pass

    def perform_post(self, path, jsonStruct = None,params=None):
        self.log.debug('Executing RestApi.__del__')

        if self.connection_url is None:
            self._set_connection_type()
        return self._perform_post( path, jsonStruct, params)

    def _perform_post(self, path, jsonStruct = None, params=None):

        headers = {'Content-type': 'application/json'}
        if self.token is not None:
            headers ['SCA-APIToken'] = str(self.token)
        path = self.connection_url+path
        self.log.debug('restApi.perform_post: json.dumps(jsonStruct): %s with path: %s ' %(json.dumps(jsonStruct), path))
        if(self.username is not None):
            res = requests.post(url= path, data=json.dumps(jsonStruct), headers=headers,auth=(self.username, self.password),params=params, verify=False)
        else:
            res = requests.post(url= path, data=json.dumps(jsonStruct), headers=headers,params=params,verify=False)
        self.log.debug('perform_post URL: %s' %res.url)
        if (not (res.status_code == 201 or res.status_code == 202 or res.status_code == 200)):
            self.log.error('Perform POST failed with status:%s for URL %s ' %(res.status_code, path))
            self.log.error(res.text)
            return None
        return res.json()

    def get_objk(self, objectName, params = None):
        self.log.debug('Executing RestApi.get_objk for objectName = %s' %objectName)
        try:
            if self.connection_url is None:
                self._set_connection_type()
            #self.connection.request("GET",  objectName)
            headers =  None
            if self.token is not None:
                headers = {'SCA-APIToken': str(self.token)}
            self.log.debug('perform_get URL: %s%s' %(self.connection_url, objectName))
            if(self.username is not None):
                resp = requests.get('%s%s' %(self.connection_url, objectName), headers=headers,auth=(self.username, self.password),params=params,verify=False, timeout=60)
            else:
                resp = requests.get('%s%s' %(self.connection_url, objectName),headers=headers,params=params,verify=False, timeout=60)

            #res = resp.text
            if ((resp.status_code != 200) and (resp.status_code != 202)) or (resp.reason != 'OK'):
                self.log.error('SCA returned an error code of: %d' %resp.status_code)
                self.log.error(resp.text)
                return None
            payload =  resp.json()
            return payload

        except Exception as e:
            self.log.error(str(e))

            self.log.error('Error in GET call of SCA')
        return None


    # virajain: added perform_delete
    def perform_delete(self, path):
        self.log.debug('Executing RestApi.perform_delete')
        if self.connection_url is None:
            self._set_connection_type()
        headers = {'Content-type': 'application/json'}
        if self.token is not None:
            headers ['SCA-APIToken'] = str(self.token)
        path = '%s%s' %(self.connection_url,path)
        if(self.username is not None):
            res = requests.delete( path, headers=headers,auth=(self.username, self.password),verify=False)
        else:
            res = requests.delete( path, headers=headers,verify=False)

        #res = self.connection.getresponse()
        if (res.status_code != 200) and (res.status_code != 202):
            self.log.debug('Perform DELETE failed with status: %s for jsonStruct ' %(res.status, jsonStruct))
            return None
        return res.json()

    def perform_put(self, path, jsonStruct = None,params=None):
        '''
        perform_put:
        Description:
            Performs the PUT operation on SCA and returns the response dict
        args:
            path:(string)valid url
            jsonStruct: (dict) data to put
            params: query parameters passed along wit URL
        '''
        self.log.debug('Executing RestApi.perform_put')
        if self.connection_url is None:
            self._set_connection_type()
        headers = {'Content-type': 'application/json'}
        #headers = {'Content-type': 'application/x-www-form-urlencoded'}
        if self.token is not None:
            headers ['SCA-APIToken'] = str(self.token)
        path = self.connection_url+path
        self.log.debug('restApi.perform_put: json.dumps(jsonStruct): %s with path: %s ' %(json.dumps(jsonStruct), path))
        if(self.username is not None):
            res = requests.put(url= path, data=json.dumps(jsonStruct), headers=headers,auth=(self.username, self.password),params=params,verify=False)
        else:
            res = requests.put(url= path, data=json.dumps(jsonStruct), headers=headers,params=params,verify=False)
        self.log.debug('perform_put URL: %s' %res.url)
        if (not (res.status_code == 201 or res.status_code == 202)):
            self.log.error('Perform PUT failed with status:%s for jsonStruct %s ' %(res.status_code, jsonStruct))
            self.log.error(res.text)
            return None
        #payload = res.text
        return res.json()

    def is_task_complete(self, taskId):
        self.log.debug('Executing RestApi.is_task_complete')
        while True:
            response = self.get_objk('/task/' + str(taskId))
            if  response == None:
                return (False, None)
            if (response['task']["ended"] == True):
                if(response['task']["nError"] == 0):
                    self.log.info('Task Completed: Response is \n %s' %response)
                    children = response['children']
                    for child in children:
                        if child['nError'] == 0:
                            return (True,response)
                        else:
                            self.log.error('Child with id %d ended with error, Error message is %s' %(child['id'],child['errorMsg']))
                            return (False,response)
                    return (True,response)
                else:
                    self.log.info('Ended with errors for /task/%s and \n the response is : %s' %(str(taskId), str(response)))
                    return (False, response)
            else:
                time.sleep(1)

    def get_dla_id(self,dlaIp):
        '''get_dla_id
            Description:
                If multiple dlas are added to sca, returns dla_id of the corresponding dlaIp
            args:
               dlaIp: ip/hostname of the dla in string format
        '''
        self.log.info('Fetching dla Id for %s' %dlaIp)
        try:
            dla_addr = socket.gethostbyname(dlaIp)
        except socket.gaierror as e:
            dla_addr = dlaIp
        url = '/dla'
        response = self.get_objk(url)
        if(response == None):
            self.log.error('Failed to fetch added dla list')
            raise RuntimeError("Failed to fetch added dla list")

        for dla_details in response:
            try:
                addr = socket.gethostbyname(dla_details['host'])
            except socket.gaierror as e:
                addr = dla_details['host']

            if(dla_addr == addr):
                return dla_details['id']

        self.log.error('Provided dla ip/hostname(%s) are not founded in added dla list' %dlaIp)
        return None

    def add_dla_to_sca(self, dlaIp, dlaPort,enable = False):
        '''add_dla_to_sca: Performs the REST post operation to add dla to sca '''
        self.log.debug('Executing RestApi.add_dla_to_sca')
        outJson = {"host": dlaIp, "port": dlaPort, "enabled": enable}
        retJson = self.perform_post('/dla', outJson)
        self.log.info('add_dla_to_sca response:')
        self.log.info(retJson)
        if retJson == None:
            return None
        dla_id = retJson['id']
        #time.sleep(70)
        #status_return = self.get_dla_status(dla_id)
        #if(False == status_return):
        #    return None
        self.log.info(retJson)
        return retJson['id']

    def get_dla_status (self, dla_id):
        self.log.info('Checking whether DLA with DLAID: %d is connected to SCA' %dla_id)
        index = 0
        while index < 30:
            response = self.get_objk('/dla/' + str(dla_id))
            self.log.info('Connection status check response:')
            self.log.info(response)
            if(response == None ):
                self.log.error('Sca returned an error while determining dla to sca connection status')
                return False
            elif ('down' == response['status']):
                self.log.debug('Sleeping for 1 second before checking again')
                time.sleep(1)
            elif ('up' == response['status']):
                self.log.info('Succesfully Added dla to sca')
                return True
            index = index+1
        if('down' == response['status']):
            self.log.error('Failed:DLA not connected to SCA ')
            #return False
            ### VAMSIII
            return True
        else:
            self.log.info('Succesfully Added dla to sca')
            return True

    def unpin_dla_id(self, dla_id):
        path = '/dla/{0}/security'.format(dla_id)
        if (self.perform_delete(path) is None):
            self.log.error('Could not unpin certificate for DLA %s' % dla_id)
            return False
        return True


    def add_ne_ip(self, ne_ip,dla_id):
        outJson = {
                  "animato": {
                      "ncc": {
                        "ne": {
                          "element_address": "%s" %ne_ip
                           }
                        }

                     }
                   }
        retJson = self.perform_put('/config/%s'%dla_id, outJson)
        self.log.info('add_ne_to_sca response:%s' %retJson)
        if retJson == None:
            self.log.error('Failed to add ne ip(%s) to sca' %ne_ip)
        self.log.info('Configured sca/viz with network element IP')
        return retJson

    def get_all_stats(self, params= None):
        self.log.info('Fetching Stats of DLAs added to SCA-%s' %self.connection_url)
        dla_stats = self.get_objk('/stats', params)
        return dla_stats

    def get_added_dlas(self):
        self.log.info('Fetching DLAs added to %s' %self.connection_url)
        return self.get_objk('/dla')

