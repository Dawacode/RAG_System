import logging

import os

class LoggerFactory:
    @staticmethod
    def get_logger(name, subsystem="app"):
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)

        for noisy_logger in ["httpcore", "hpack", "httpx"]:
            logging.getLogger(noisy_logger).setLevel(logging.WARNING)
            
        return logger

def get_logger(name, subsystem="app"):
    return LoggerFactory.get_logger(name, subsystem)