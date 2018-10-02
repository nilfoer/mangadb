import os.path
import logging
import logging.config


def configure_logging(log_path):
    logging.config.dictConfig({
        'version': 1,
        'formatters': {
            'console': {'format': '%(asctime)s - %(levelname)s - %(message)s', 'datefmt': "%H:%M:%S"},
            "file": {"format": "%(asctime)-15s - %(name)-9s - %(levelname)-6s - %(message)s"}
        },
        'handlers': {
            'console': {
                'level': 'INFO',
                'class': 'logging.StreamHandler',
                'formatter': 'console',
                'stream': 'ext://sys.stdout'
            },
            'file': {
                'level': 'DEBUG',
                'class': 'logging.handlers.RotatingFileHandler',
                'formatter': 'file',
                'filename': log_path,
                'maxBytes': 1048576,
                'backupCount': 5,
                "encoding": "UTF-8"
            }
        },
        'loggers': {
        },
        "root": {
                'level': 'DEBUG',
                'handlers': ['console', 'file']
        },
        'disable_existing_loggers': False
    })


# log to dir of package but set actual logging loc to working dir when called
# as script (done in main)
configure_logging(os.path.join(os.path.dirname(os.path.realpath(__file__)), "manga_db.log"))
