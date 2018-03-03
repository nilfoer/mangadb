#!/usr/bin/python
 # -*- coding: UTF-8 -*-
 
import cgi
import sys

def output(content):
	sys.stdout.write('Content-Type: text/plain\n\n')
	sys.stdout.write(content)

form = cgi.FieldStorage()

fail=0
try:
	myData = str(form['myData'].value)
except:
	fail=1
else:
	if myData == "":
		fail=1

if fail == 1:
	output('Who are you?')
	raise SystemExit

output('Hello, '+myData)
raise SystemExit