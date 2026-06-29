import logging
import logging.config
import sys
import os
from configuration.manger_config import config


def setup_logging():
    log_to_console = config.log_to_console

    log_directory = "logs"

    os.makedirs(log_directory, exist_ok=True)

    log_file_path = os.path.join(log_directory, "heartgold.log")

    active_handlers = ['file']
    if log_to_console:
        active_handlers.append('console')

    LOGGING_CONFIG = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'detailed': {
                'format': '%(asctime)s - %(name)-25s - %(processName)-15s - %(levelname)-8s - %(message)s'
            },
            'simple': {
                'format': '%(levelname)-8s - %(message)s'
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'INFO',
                'formatter': 'simple',
                'stream': sys.stdout,
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'DEBUG',
                'formatter': 'detailed',
                'filename': log_file_path,
                'maxBytes': 10485760,
                'backupCount': 5,
                'encoding': 'utf-8',
            },
        },
        'root': {
            'level': 'WARNING',
            'handlers': active_handlers,
        },
        'loggers': {

            'operation_modules': {
                'level': 'DEBUG',
                'handlers': active_handlers,
                'propagate': False,
            },
            'director_main': {
                'level': 'DEBUG',
                'handlers': active_handlers,
                'propagate': False,
            },
        }
    }
    logging.config.dictConfig(LOGGING_CONFIG)
