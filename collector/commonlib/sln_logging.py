#
# SLN Logging for install/upgrade automation
#                                                                                 #
# Copyright (c) 2016 by cisco Systems, Inc.
# All rights reserved. This program contains proprietary
# and confidential information.
#--------------------------------------------------------------
#
import logging
import sys

class SlnLogging(object):
    '''All logging customization required by all module will be done here '''

    logging_level = logging.DEBUG
    #logging_level = None
    log_file_descriptor = None 
    g_out_handler = None
     
    @staticmethod
    def get_sln_logger(in_name,in_logging_level = None):
        ''' 
        get_sln_logger:
        Description:
            creates a log obj. sets the name and logging level 
        args:
        in_name           : name of the file/module name which is calling this function
        in_loging_level   : logging level to be set. Apart from the very first call other calls are expected to be None
        '''
        log = logging.getLogger(in_name)

        if(in_logging_level is not None):
            SlnLogging.logging_level = in_logging_level
        
        log.setLevel(SlnLogging.logging_level)
        return log

    @staticmethod
    def set_outHandler(in_log):
        '''
        set_outHandler:
        Description:
           sets the stdout handler for the log

        args:
           in_log   : logger object to which std handlr is set to
        ''' 
        StreamHandler = logging.StreamHandler
        if( SlnLogging.log_file_descriptor is not None):
            handler = StreamHandler(SlnLogging.log_file_descriptor)
        handler_stdout = StreamHandler(sys.stdout)
        
        date_format = '%Y-%m-%dT%H:%M:%S'
        log_format = '%(asctime)s: %%%(name)s-%(levelname)s: %(message)s'
        Formatter = logging.Formatter(fmt = log_format, 
                         datefmt = date_format )

        # add handler to logger
        if( SlnLogging.log_file_descriptor is not None):
            handler.setFormatter(Formatter)
            in_log.addHandler(handler)
        
        handler_stdout.setFormatter(Formatter)
        in_log.addHandler(handler_stdout)

    @staticmethod
    def set_file_handler(in_log,fd):
        '''
        set_file_handler
        Description:
           sets the file  handler for the log. All logging created using this log will be written to fd 
        args:
           in_log   : logger object to which fd handler is set to
           fd: file descriptor to which logging is written 
        ''' 
        StreamHandler = logging.StreamHandler
        handler = StreamHandler(fd)
        
        date_format = '%Y-%m-%dT%H:%M:%S'
        log_format = '%(asctime)s: %%%(name)s-%(levelname)s: %(message)s'
        Formatter = logging.Formatter(fmt = log_format, 
                         datefmt = date_format )

        # add handler to logger
        handler.setFormatter(Formatter)
        in_log.addHandler(handler)
