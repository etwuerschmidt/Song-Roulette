#!/bin/sh
#Installation for all python modules in repo
#A single module can be specified for install as a command line argument 
MOD1=${1:-none}
for file in *; do
	if [[ -d $file ]]; then
		if [[ "$MOD1" != "none" ]]; then
			if [[ "$file" == "$MOD1" ]]; then
				echo "Installing module for $file"
				cd $file
				python setup.py install > $file.install.log
				cd ..
				echo "Installation complete"
				exit
			fi
		else
			cd $file
			if [[ -f setup.py ]]; then
				echo "Installing module for $file"
				python setup.py install > $file.install.log
			fi
			cd ..
		fi
	fi
done
echo "Installation complete"
exit