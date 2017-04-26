This script polls a set of SNMP mibs and dumps the data as a flat file.
In order to run this script, some dependencies have to be met.
The collection script needs to be run with python3

sudo apt-get install python3-pip
pip3 install pysnmp
pip3 install pysmi
pip3 install pyyaml

before running the script, the python libraries implementing the WLC mibs have to be compiled
This is done by running python setup.py from this directory (snmp_poll).
Notice that the script assumes mibdump.py to be installed in /usr/local/bin/. Typically this is the default path of the pysmi package, but if it is not the case the path in the setup script has to be fixed.
Notice that the setup script (unlike the polling script) can be run with python 2.7

The parameters of SNMP polling are defined in a yaml file. ../config/snmp_lab.yml can be used as a template

The configuration file is made up of two sections. The first section (snmp_mibs) described the MIBs which are polled. Unless  there is a specific reason, the same list as in the example file should be used.
The second section (snmp_agents) described the WLCs which will be polled and their respective paramters.
In particular, the most relevant parameters are

## this represents the network endpoint where the SNMP agent is listening
     ip: sln-wlab-gw
     port: 2161
### this is the time interval used for SNMP polling (in seconds). All of the mibs will be polled with the same frequency
     check_interval: 30
### SNMP community string
     community_data: public


the script will be run as follows
python3 poll_mibs.py <path to configuration yaml file>

When running, the script will create a ./data directory and populate it with files whose name will look like the following

data/data_wlc_2_1474905420.dat