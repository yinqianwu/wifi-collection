#
# SLN Parameter Parsing
#
# Copyright (c) 2016 by cisco Systems, Inc.
# All rights reserved. This program contains proprietary
# and confidential information.
#--------------------------------------------------------------
#
import sys
import logging
import getpass
import re
import os

from commonlib.sln_logging import SlnLogging

log = SlnLogging.get_sln_logger("main",logging.INFO)

# paramsDescriptionMap {paramName: (paramPath, validationFunc, canBeEmpty}
def obj_path_string(pathVec):
    return ':'.join([str(x) for x in pathVec])

def prompt_password(in_prompt):
    for _ in range(0,3):
        password1 = getpass.getpass(prompt=in_prompt)
        password2 = getpass.getpass(prompt='Confirm Password:')
        if password1 == password2:
            break
        else:
            print('Password does not match, please try again')
    else:
        log.error('Number of tries Exceeded. Exiting with error code')
        sys.exit(-1)
    return password1

class ParamsMap:
    def __init__(self, descriptionMap, defaultValues, loggingString = '', ignoreMissing = False):
        self.descriptionMap = {d.name : d for d in descriptionMap}
        self.defaultValues = defaultValues
        self.readValues = None
        self.loggingString = loggingString
        self.ignoreMissing = ignoreMissing
        self.interfacesList = set([])

    def read_input_values(self, decodedYaml):
        self.readValues = {}
        for paramName, desc in self.descriptionMap.items():
            paramPath = desc.path
            validationFunc = desc.validationFunc
            currentSection =  decodedYaml
            curObj =  decodedYaml
            objVal = None
            pathSeen = []
            for p in paramPath:
                if not isinstance(curObj, dict):
                    log.error('%s : Value of %s is missing or invalid', self.loggingString,obj_path_string(pathSeen))
                    sys.exit(-1)
                if p not in curObj:
                    curObj = None
                    break
                curObj = curObj[p]
                pathSeen.append(p)
            objVal = curObj

            if (objVal is not None):
                if (validationFunc is not None):
                    (ret, err) = validationFunc(objVal)
                    if not ret:
                        log.error("%s: Field '%s' is invalid. %s", self.loggingString,
                                  obj_path_string(paramPath), err)
                        sys.exit(-1)
            elif(self.defaultValues is not None):
                if (paramName in self.defaultValues):
                    objVal = self.defaultValues[paramName]
            if (objVal is None):
                    if (desc.passwordPrompt is not None):
                        objVal = prompt_password(desc.passwordPrompt)
                    elif (desc.inPrompt is not None):
                        objVal = input(desc.inPrompt)
                    elif (desc.constDefault is not None):
                        objVal = desc.constDefault
            if (objVal is None or objVal == "") and (not self.ignoreMissing) and desc.failIfMissing:
                log.error('%s : No value for required field %s' % (self.loggingString,obj_path_string(paramPath)))
                sys.exit(-1)
            if (desc.isInterface):
                if isinstance(objVal, list):
                    if len(objVal) is 0:
                        log.error('%s : Empty interface list for %s', self.loggingString,
                                  obj_path_string(paramPath))
                        sys.exit(-1)
                    self.interfacesList.update(objVal)
                else:
                    self.interfacesList.update([objVal])

            self.readValues[paramName] = objVal
        return self.readValues

    def mentioned_interfaces_list(self):
        return list(self.interfacesList)

class ConfDescription:
    def __init__(self, name, path, validationFunc = None, failIfMissing = True,
                 passwordPrompt = None, inPrompt = None, constDefault = None, isInterface = False):
        self.name = name
        self.path = path
        self.validationFunc = validationFunc
        self.failIfMissing = failIfMissing
        self.passwordPrompt = passwordPrompt
        self.inPrompt = inPrompt
        self.constDefault = constDefault
        self.isInterface = isInterface

def ip_string_to_binary(ipString):
    tokenizedIp = [int(t) for t in ipString.split('.')]
    tokenizedIp = [i for i in reversed(tokenizedIp)]
    binaryIp = 0
    for i in range(0,4):
        binaryIp += tokenizedIp[i] << (i * 8)
    return binaryIp

def inverse_netmask_from_prefix_len(length):
    return ((1 << (32 - length)) -1) & 0xffffffff
def netmask_from_prefix_len(length):
    # print length
    return inverse_netmask_from_prefix_len(length) ^ 0xffffffff

def is_ip_address(arg):
    if (isinstance(arg, str)):
        tokens = arg.split('.')
        if (len(tokens) == 4):
            argOk = True
            for t in tokens:
                if (t.isdigit()):
                    tval = int(t)
                    if (tval < 0) or (tval > 255):
                        argOk = False
                        break
                else:
                    argOk = False
                    break
            if (argOk):
                return (True,'')
    return (False, 'Value "%s" is not a valid IP address' % arg)

def is_netmask(arg):
    if is_ip_address(arg):
        need_zero = False
        for octet in [int(x) for x in arg.split('.')]:
            if (-octet & (octet^255)) != 0 or (octet != 0 and need_zero):
                break
            need_zero = (octet != 255)
        else:
            return (True,'')
    return (False, 'Value "%s" is not a valid netmask' % arg)

def is_valid_hostname(arg):
    (ret, err) = is_ip_address(arg)
    if ret:
        return (False, 'Value "%s" appears to be an IP addres, not a hostname' % arg)
    return is_valid_host_or_ip(arg)

def is_valid_host_or_ip(arg):
    if len(arg) > 255:
        return False
    if arg[-1] == ".":
        arg = arg[:-1]
    allowed = re.compile("(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
    if all(allowed.match(x) for x in arg.split(".")):
        return (True, "")
    return (False, 'Value "%s" is not a valid hostname' % arg)

def is_valid_directory(arg):
    if (os.path.isdir(arg)):
        return (True, "")
    return (False, "Not a valid dir: " + arg)



serverArgs = [
    ConfDescription("ip",['ip'], validationFunc = is_valid_host_or_ip),
    ConfDescription("api_version",['api_version'], constDefault = 'v1'),
    ConfDescription("check_interval",['check_interval'], constDefault = 10),
    ConfDescription("base_path",['base_path']),
    ConfDescription("port",['port'], failIfMissing = False),
    ConfDescription("username",['username'], inPrompt = True),
    ConfDescription("password",['password'], passwordPrompt = True),
    ConfDescription("data_prefix",['data_prefix'], failIfMissing = False)
]


dataListArgs = [
    ConfDescription("api_path",['api_path']),
    ConfDescription("timestamp_field",['timestamp_field'], failIfMissing = False),
    ConfDescription("check_interval",['check_interval']),
    ConfDescription("check_window",['check_window']),
    ConfDescription("only_associated",['only_associated'], constDefault = False)
]


generalArgs = [
    ConfDescription("log_directory",['log_directory'], validationFunc = is_valid_directory),
    ConfDescription("data_directory",['data_directory'], validationFunc = is_valid_directory),
    ConfDescription("data_file_rotation_thr",['data_file_rotation_thr']),
]


containerArgsDesc = [
ConfDescription("wlc_hostname",['wlc_hostname'], validationFunc = is_valid_host_or_ip),
ConfDescription("wlc_username",['wlc_username']),
ConfDescription("wlc_password",['wlc_password'], failIfMissing = False),
ConfDescription("wlc_ssh_port",['wlc_ssh_port'], constDefault = 22),
ConfDescription("data_collection_duration",['data_collection_duration']),
ConfDescription("data_collection_interval",['data_collection_interval']),
ConfDescription("inter_cli_interval",['inter_cli_interval'], failIfMissing = False)
]


