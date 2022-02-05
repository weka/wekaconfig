import logging
import logging.handlers
import platform


def configure_logging(logger, verbosity):
    loglevel = logging.INFO  # default logging level
    libloglevel = logging.ERROR

    # default message formats
    console_format = "%(message)s"
    # syslog_format =  "%(levelname)s:%(message)s"

    syslog_format = "%(process)s:%(filename)s:%(lineno)s:%(funcName)s():%(levelname)s:%(message)s"

    if verbosity == 1:
        loglevel = logging.INFO
        console_format = "%(levelname)s:%(message)s"
        syslog_format = "%(process)s:%(filename)s:%(lineno)s:%(funcName)s():%(levelname)s:%(message)s"
        libloglevel = logging.INFO
    elif verbosity == 2:
        loglevel = logging.DEBUG
        console_format = "%(filename)s:%(lineno)s:%(funcName)s():%(levelname)s:%(message)s"
        syslog_format = "%(process)s:%(filename)s:%(lineno)s:%(funcName)s():%(levelname)s:%(message)s"
    elif verbosity > 2:
        loglevel = logging.DEBUG
        console_format = "%(filename)s:%(lineno)s:%(funcName)s():%(levelname)s:%(message)s"
        syslog_format = "%(process)s:%(filename)s:%(lineno)s:%(funcName)s():%(levelname)s:%(message)s"
        libloglevel = logging.DEBUG

    # create handler to log to console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(console_format))
    logger.addHandler(console_handler)

    # create handler to log to syslog
    logger.info(f"setting syslog on {platform.platform()}")
    if platform.platform()[:5] == "macOS":
        syslogaddr = "/var/run/syslog"
    else:
        syslogaddr = "/dev/log"
    syslog_handler = logging.handlers.SysLogHandler(syslogaddr)
    syslog_handler.setFormatter(logging.Formatter(syslog_format))

    # add syslog handler to root logger
    if syslog_handler is not None:
        logger.addHandler(syslog_handler)

    # set default loglevel
    logger.setLevel(loglevel)

    logging.getLogger("wekalib").setLevel(logging.ERROR)
    logging.getLogger("wekalib.wekaapi").setLevel(libloglevel)  # should leave at INFO as default
    logging.getLogger("wekalib.wekacluster").setLevel(libloglevel)
    logging.getLogger("wekalib.sthreads").setLevel(logging.ERROR)  # should leave at ERROR as default
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("pssh").setLevel(logging.ERROR)

    # local modules
    logging.getLogger("wekaconfig").setLevel(loglevel)
    logging.getLogger("weka").setLevel(loglevel)
    logging.getLogger("logic").setLevel(loglevel)
    logging.getLogger("output").setLevel(loglevel)
    logging.getLogger("apps").setLevel(loglevel)
    logging.getLogger("forms").setLevel(loglevel)
