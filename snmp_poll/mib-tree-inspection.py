# SNMP manager-side MIB management
from pysnmp.hlapi import *

from pysnmp.smi import builder, view, compiler, error
from pysnmp.entity.rfc3413.oneliner import cmdgen
import xlsxwriter
import os

# Create MIB loader/builder
mibBuilder = builder.MibBuilder()
builder.MibBuilder.loadTexts = 1

pythonMibsDir = os.path.join(os.path.expanduser("~"), '.pysnmp' , 'mibs')

print('Setting MIB sources...')
mibBuilder.addMibSources(builder.DirMibSource(pythonMibsDir))
print(mibBuilder.getMibSources())
print('done')

treesToPoll = []

for filename in os.listdir(pythonMibsDir):
    if not filename.endswith('.py'):
        continue
    treesToPoll.append(filename[:-3])



class ExcelOutput:
    workbook = None

    def __init__(self, sheetName):
        self.worksheet = ExcelOutput.workbook.add_worksheet(sheetName)
        self.curLine = 0


    def add_row(self, values):
        for i, v in enumerate(values):
            if v is not None:
                self.worksheet.write_string(self.curLine, i, v)

        self.curLine += 1

def print_mib_documentation(sheet, mibView, mibName):

    try:
        oid, label, suffix = mibView.getFirstNodeName(modName=mibName)
        lastOid,  _, _ = mibView.getLastNodeName(modName=mibName)

        while 1:
            modName, nodeDesc, suffix = mibView.getNodeLocation(oid)
            oidStr = '.'.join([str(i) for i in list(oid)])

            # print('%s::%s == %s' % (modName, nodeDesc, oid))
            modName, symName, suffix = mibView.getNodeLocation(oid)
            rowNode, = mibBuilder.importSymbols(modName, symName)
            if hasattr(rowNode, 'getDescription'):
                desc = rowNode.getDescription()
                convertedL = [t.lstrip('\t ').rstrip(' ') for t in desc.split('\n')]
                # for l in convertedL:
                #     print repr(l)
                converted = ' '.join(convertedL)
                desc = converted
            else:
                desc = ''
            sheet.add_row([modName, nodeDesc, oidStr, desc])

            if oid >= lastOid:
                break
            oid, label, suffix = mibView.getNextNodeName(oid)
    except error.SmiError as e:
        print 'Exception'  + str(e)
        return
    print 'OK'

print('Loading MIB modules...'),
mibBuilder.loadModules(
    *tuple(treesToPoll)
    )
print('done')
print('Indexing MIB objects...'),
mibView = view.MibViewController(mibBuilder)
print('done')



ExcelOutput.workbook = xlsxwriter.Workbook('mibs_desc.xlsx')

outSheet = ExcelOutput('mibs')
outSheet.add_row(['MIB' ,'node name', 'OID', 'description'])

for mibName in treesToPoll:
    print '*' * 100
    print mibName
    print_mib_documentation(outSheet, mibView, mibName)
ExcelOutput.workbook.close()

