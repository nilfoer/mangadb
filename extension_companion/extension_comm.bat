@echo off
REM Note for Windows: in the example above, the native application is a Python script. It can be difficult to get Windows to run Python scripts reliably in this way, so an alternative is to provide a .bat file, and link to that from the manifest

call python -u "N:\\coding\\tsu-info\\run_ext_companion.py"