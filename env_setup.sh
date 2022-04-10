#!/bin/bash

cp ./autocheck.py ./qkd
cp ./test_case.py ./qkd

var="$(qne application init qkd)"

if [[ $var =~ "already exists" ]]; then
	echo FAIL
	echo Please modify your qne environment file if needed
	echo Opening default, ~/.qne/applications.json, in nano
	read -p "Press enter to continue ..."
	nano ~/.qne/applications.json
	qne application init qkd
else
	echo OK
fi
