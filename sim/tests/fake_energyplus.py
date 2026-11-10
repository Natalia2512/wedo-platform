#!/usr/bin/env python3
"""Stand-in for EnergyPlus used ONLY to test wedo_sim.py when EnergyPlus is not installed.
It reads the EPW temperatures and writes an eplusout.sql with the tables the runner queries."""
import sqlite3, sys
from pathlib import Path
if "--version" in sys.argv:
    print("EnergyPlus, Version 24.2.0-fake"); sys.exit(0)
a = sys.argv; epw = Path(a[a.index("--weather") + 1]); out = Path(a[a.index("--output-directory") + 1])
temps = [float(l.split(",")[6]) for l in epw.read_text().splitlines()[8:]]
db = sqlite3.connect(out / "eplusout.sql"); c = db.cursor()
c.execute("CREATE TABLE Time(TimeIndex INTEGER, WarmupFlag INTEGER)")
c.execute("CREATE TABLE ReportDataDictionary(ReportDataDictionaryIndex INTEGER, IsMeter INTEGER, KeyValue TEXT, Name TEXT, ReportingFrequency TEXT)")
c.execute("CREATE TABLE ReportData(ReportDataIndex INTEGER, TimeIndex INTEGER, ReportDataDictionaryIndex INTEGER, Value REAL)")
c.execute("CREATE TABLE TabularDataWithStrings(ReportName TEXT, TableName TEXT, RowName TEXT, ColumnName TEXT, Value TEXT)")
c.execute("INSERT INTO TabularDataWithStrings VALUES('AnnualBuildingUtilityPerformanceSummary','Building Area','Total Building Area','Area','500.00')")
c.executemany("INSERT INTO ReportDataDictionary VALUES(?,?,?,?,?)",
    [(1,1,None,"Heating:EnergyTransfer","Hourly"),(2,1,None,"Cooling:EnergyTransfer","Hourly"),
     (3,0,"FLAT_A","Zone Operative Temperature","Hourly"),(4,0,"FLAT_B","Zone Operative Temperature","Hourly")])
rows=[]
for i,t in enumerate(temps,1):
    c.execute("INSERT INTO Time VALUES(?,0)",(i,))
    rows += [(i*4,i,1,max(0,18-t)*500*3600*1.5),(i*4+1,i,2,max(0,t-22)*500*3600*2),
             (i*4+2,i,3,t+6),(i*4+3,i,4,t+8)]
c.executemany("INSERT INTO ReportData VALUES(?,?,?,?)",rows); db.commit()
(out/"eplusout.err").write_text("Program Version,EnergyPlus fake\n   ************* EnergyPlus Completed Successfully.\n")
