from .logging_setup import configure_logging

# packaging.version.parse:
# parse('0.24.0') < parse("0.231.0") = True
VERSION = '0.24.0'

configure_logging("manga_db.log")
