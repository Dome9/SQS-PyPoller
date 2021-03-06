#!/usr/bin/python

# ******************************************************************************
# Name: sqs-py-poller
# Description: A simple AWS sqs message poller with configurable logging
# Author: Roy Feintuch (froyke)
#
# Copywrite 2015, Dome9 Security
# www.dome9.com - secure your cloud
# ******************************************************************************

import boto
import json
import time
import sys
import socket
import ConfigParser
import logging
from datetime import datetime
from boto.sqs.message import RawMessage

logger = logging.getLogger('poller')

def run():
    print "starting SQS poller script"
    forever= any("forever" in s for s in sys.argv)
    if forever: print "running forever "
    start = datetime.now()
    MAX_WORKER_UPTIME_SECONDS = 60 #when not running forever...
    
    # load config file
    config = ConfigParser.ConfigParser()
    config.read("./poller.conf")
    
    # Set up logging
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    
    if config.getboolean('console','enabled'):
        consoleHdlr = logging.StreamHandler(sys.stdout)
        consoleHdlr.setLevel(logging.DEBUG)
        logger.addHandler(consoleHdlr) 
    
    if config.getboolean('file_logger','enabled'):
        logPath = config.get('file_logger','logPath')
        hdlr = logging.FileHandler(logPath)
        hdlr.setFormatter(formatter)
        hdlr.setLevel(logging.INFO)
        logger.addHandler(hdlr)
    
    if config.getboolean('syslog','enabled'):
        host = config.get('syslog', 'host')
        port = config.getint('syslog','port')
        syslogHdlr = logging.handlers.SysLogHandler(address=(host,port), socktype=socket.SOCK_DGRAM)
        syslogHdlr.setFormatter(formatter)
        syslogHdlr.setLevel(logging.INFO)
        logger.addHandler(syslogHdlr) 
    
    # Init AWS SQS
    AWSKey = config.get('aws', 'key')
    AWSSecret = config.get('aws','secret')
    queueName = config.get('aws', 'queue_name')
    queueRegion = config.get('aws', 'region')
    sqs = boto.sqs.connect_to_region(queueRegion, aws_access_key_id=AWSKey, aws_secret_access_key=AWSSecret)
    
    # TODO - proper error handling. Probably faulty IAM configuration
    q = sqs.get_queue(queueName)
    if  not q: # fallback for some IAM configurations. see: https://github.com/boto/boto/issues/653
        logger.debug("could not get Q by name, will try to search all queues")
        all_queues = sqs.get_all_queues()
        logger.debug(all_queues)
        q = [q for q in all_queues if queueName in q.name][0]
    
    q.set_message_class(RawMessage)
    
    # Poll messages loop
    while True:
        result_count = 0
        try:
            results = q.get_messages(10, wait_time_seconds=20)
            result_count = len(results)
            logger.debug( "Got %s result(s) this time." % result_count)
    
            for result in results:
                try:
                    handleMessage(result)
                    #result.delete()
                except:
                    logger.exception("Error while handling messge:\n{}'".format(result.get_body()))
                finally:
                    result.delete() #this will delete all messages even if their handling failed. For additional reliability you can move this to the try block. (and then configure dead letter queue to handle 'poisonous messages')
            
            #if not forever and len(results) == 0:
            #    break
        except (socket.gaierror):
            time.sleep(30)
        except:
            logger.exception("Unexpected error. Will retry in 60 seconds")
            time.sleep(60)
        finally:
            if not forever:
                if (datetime.now()-start).total_seconds() > MAX_WORKER_UPTIME_SECONDS:
                    logger.debug("Worker uptime exceeded. exiting.")
                    break
                if result_count==0:
                    logger.debug("Queue is empty. exiting.")
                    break


def handleMessage(result):
    '''This is the place to handle each message. 
    This is the place to customize and write specific message handling logic like sending this message to external system
    or perfroming addiitonal filtering for specific message types.
    ''' 
    msg = json.loads(result.get_body())["Message"] # Assuming this is a JSON SQS message received form SNS. AWS SNS can send raw messages so this line is not needed. See:http://docs.aws.amazon.com/sns/latest/dg/SNSMessageAttributes.html
    #msg = result.get_body() # this is when you are working in RAW mesage mode.
    logger.info(msg) # this is the default handling - send to the logger



if __name__ == '__main__': run()
