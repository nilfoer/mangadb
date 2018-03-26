@echo off
REM ^^ otherwise REM comments will be displayed
REM src: https://stackoverflow.com/questions/2323292/assign-output-of-a-program-to-a-variable
REM Note that the first % in %%i is used to escape the % after it and is needed when using the above code in a batch file rather than on the command line
REM Doesnt work for lines with spaces: for /f %%i in ('python -c "import os, sys; print(' '.join('{}'.format(d) for d in sys.path if os.path.isdir(d)))"') do set module_locs=%%i
REM src: https://stackoverflow.com/questions/6359820/how-to-set-commands-output-as-a-variable-in-a-batch-file
REM I always use the USEBACKQ so that if you have a string to insert or a long file name, you can use your double quotes without screwing up the command.
REM FOR /F "tokens=* USEBACKQ" %%F IN (`command`) DO (SET var=%%F)
REM Note that if your command includes a pipe then you need to escape it with a caret, for example: for /f "delims=" %%a in ('echo foobar^|sed -e s/foo/fu/') do @set foobar=%%a
REM for /f "delims=" %%a in ('ver') do @set foobar=%%a // src: https://stackoverflow.com/questions/889518/windows-batch-files-how-to-set-a-variable-with-the-result-of-a-command
REM python cmd gets locations where python searches for modules
for /f "delims=" %%a in ('python -c "import os, sys; print(' '.join('{}'.format(d) for d in sys.path if os.path.isdir(d)))"') do @set module_locs=%%a
REM -R -> recursive search of dirs supplied on cmdline; -f path/to/output-tagfile; %CD% -> var for current dir
REM %module_locs% contains python module paths seperated by spaces
ctags -R --fields=+l --languages=python --python-kinds=-iv -f %USERPROFILE%\tags %CD% %module_locs%
REM src: https://www.fusionbox.com/blog/detail/navigating-your-django-project-with-vim-and-ctags/590/

REM src: http://www.held.org.il/blog/2011/02/configuring-ctags-for-python-and-vim/
REM ctags has a little downside when using Python: it recognizes import lines as a definition, at least as of ctags v5.8. No need to explain why it's annoying in most cases. After 2 years of suffering, I've found it's possible to overcome this simply by adding the --python-kinds=-i option to the command line, or better: to ~/.ctags.
REM optional: --exclude=<partial names of bad files/directories>. e.g. --exclude=*/build/* to exclude all files inside 'build/' directories
