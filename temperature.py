#!/usr/bin/env python
#exit()

import os
os.chdir("/home/pi/station-meteo")

#import sys
#sys.stdout = open('/home/pi/station-meteo/temperature.log', 'w')

import datetime
import sqlite3
import serial
from serial import Serial
import I2C_LCD_driver
import time
import atexit
import threading
import wiringpi
import RPi.GPIO as GPIO
GPIO.setmode (GPIO.BOARD) 
import json
import Adafruit_MPR121.MPR121 as MPR121
import ephem
import math
import wget
#import ssl

#from Tkinter import * 
import itertools
import bme280


# import AzureIOT
import base64
import hmac
import six.moves.urllib as urllib 
import paho.mqtt.client as mqtt
import time
from confclient import *


from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy import create_engine, MetaData, Table, Column, ForeignKey,Integer, String,Boolean
from sqlalchemy.ext.declarative import declarative_base

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor

from pytz import utc
Base = declarative_base()
metadata = MetaData()


sleeping2 = False

def logMsg (message):
	print (time.strftime('%Y-%m-%d_%H:%M:%S') + "   " + message)

logMsg ("Variable initialisation")



## Variables
gtkline1=""
gtkline2=""
gtkline3=""
gtkline4=""

dbname='./database/dataenv'
confdbname='./database/conf.db'
isstleurl="https://www.celestrak.com/NORAD/elements/stations.txt"
tledirectory="./tle/"
isstelefile = "iss_tle.txt"
elevation = 216 #altitude en metres : 189 m + 9 x 3m
pressureelevation= 0.12
gpioKeyboard=40 #ou 13


#Variables Azure IOT
#hubAddress = "XFAIOTHUB1.azure-devices.net"
#deviceId = "rpi1"
#deviceKey = 'bAPQ0uQmsSotmEEoDCGtNfVReYYNxq8i4SJVh0dwI58='

#hubUser = hubAddress + '/' + deviceId
#endpoint = hubAddress + '/devices/' + deviceId
#hubTopicPublish = 'devices/' + deviceId + '/messages/events/'
#hubTopicSubscribe = 'devices/' + deviceId + '/messages/devicebound/#'






logMsg ("Scheduler initialisation")

# initalisation du scheduler
jobstores = {
    'default': SQLAlchemyJobStore(url="sqlite:///" + confdbname)
}
executors = {
    'default': ThreadPoolExecutor(20),
    'processpool': ProcessPoolExecutor(5)
}
job_defaults = {
    'coalesce': False,
    'max_instances': 3
}
scheduler = BackgroundScheduler(jobstores=jobstores, executors=executors, job_defaults=job_defaults, timezone=utc)





# Initialisation des PIN

buzzer_pin = 22 #15
logMsg ("Initializing buzzer PIN " + str(buzzer_pin))
GPIO.setup(buzzer_pin, GPIO.OUT)


curtemp1 = ""
curvoltage1=""

# boutons sur le PCDUINO
ButtonMenu=2
ButtonDown=4
ButtonOK=5

#Initialisation Boutons mpr121
keypad= dict ()
keypad= {"button_up":16,"button_down":64,"button_left":512,"button_right":2,"button_ok":32,"button_lock":256,"button_sleep":1}
#keypad= {"button_up":4096,"button_down":16384,"button_left":2,"button_right":512,"button_ok":8192,"button_lock":256}
probe1id="ID=2DFC"

txcmd= list()





#initialisation du scheduler



#fonctions astro

def astro_ephemplanet (planet):
	planetObject = ""
	if planet == "Moon":
		planetObject = ephem.Moon()
	if planet == "Sun":
		planetObject = ephem.Sun()
	if planet == "Venus":
		planetObject = ephem.Venus()
	if planet == "Jupiter":
		planetObject = ephem.Jupiter()
	if planet == "Saturn":
		planetObject = ephem.Saturn()
	if planet == "Mars":
		planetObject = ephem.Mars()
	if planet == "Mercure":
		planetObject = ephem.Mercury()
	return planetObject





def astro_planetnexttransit (planet):
	location = astro_obslocation ("OULLINS")
	eventdate =ephem.localtime (ephem.Date (location.next_transit(astro_ephemplanet (planet))))
	location.date = datetime.datetime.utcnow()
	return "TR: " + eventdate.strftime('%b %d %H:%M:%S')

def astro_planetnextrising (planet,utc=False):
	location = astro_obslocation ("OULLINS")
	eventdateutc =location.next_rising(astro_ephemplanet (planet))
	eventdate =ephem.localtime (ephem.Date (eventdateutc))
	location.date = datetime.datetime.utcnow()
	if not utc:
		return "R: " + eventdate.strftime('%b %d %H:%M')
	else:
		return str (eventdateutc).replace ("/","-")
		
def astro_planetnextsetting (planet):
	location = astro_obslocation ("OULLINS")
	eventdate =ephem.localtime (ephem.Date (location.next_setting(astro_ephemplanet (planet))))
	return "S: " + eventdate.strftime('%b %d %H:%M')
	location.date = datetime.datetime.utcnow()

def astro_planetazimuth (planet):
	location = astro_obslocation ("OULLINS")
	degrees_per_radian = 180.0 / math.pi
	ephobject = astro_ephemplanet (planet)
	location.date = datetime.datetime.utcnow()
	ephobject.compute(location)

	return ('ALT:%4.1f AZ:%5.1f' % (ephobject.alt * degrees_per_radian, ephobject.az * degrees_per_radian))	



def astro_satellitenextpass (satname,data,utc=False):
	global satellite_tle
	exitloop = False
	location = astro_obslocation ("OULLINS")
	satellite = ephem.readtle (astro_satTLE ("ISS")[0],astro_satTLE ("ISS")[1],astro_satTLE ("ISS")[2])
	looptime = ephem.now()
	while not exitloop:
		satellite.compute(location)
		location.date = looptime
		satellite.compute(location)
		nxpass= location.next_pass (satellite)

		
		if astro_satellitevisible (satname, "OULLINS", nxpass [2]) == "V":
			#logMsg ("ISS NextPass : " + str(nxpass [2]))
			#logMsg ("ISS Magnitude" + str(astro_satelliteMagnitude(satname, "OULLINS", nxpass [2])))
			#logMsg ("ISS Coord :" + str(astro_satelliteazimuth (satname,  "OULLINS", nxpass [2])))
			
			exitloop = True
		else:

			looptime = nxpass [4]
			exitloop = False
		
	if not utc:
		if data  ==  "rise_time":
			return ephem.localtime (nxpass [0]).strftime('%Y-%m-%d %H:%M:%S')
		if data ==  "rise_azimuth":
			return astro_satelliteazimuth (satellite, location, nxpass [0])
		if  data == "maximum_altitude_time":
			return ephem.localtime (nxpass [2]).strftime('%Y-%m-%d %H:%M:%S')
		if data ==  "maximum_altitude":
			return astro_satelliteazimuth (satellite, location, nxpass [2])
		if data ==  "set_time":
			return ephem.localtime (nxpass [4]).strftime('%Y-%m-%d %H:%M:%S')
		if data ==  "set_azimuth":
			return astro_satelliteazimuth (satellite, location, nxpass [4])
	else:
		if data  ==  "rise_time":
			return str (nxpass [0]).replace ("/","-")
		if data ==  "rise_azimuth":
			return astro_satelliteazimuth (satellite, location, nxpass [0])
		if  data == "maximum_altitude_time":
			return str (nxpass [2]).replace ("/","-")
		if data ==  "maximum_altitude":
			return astro_satelliteazimuth (satellite, location, nxpass [2])
		if data ==  "set_time":
			return str (nxpass [4]).replace ("/","-")
		if data ==  "set_azimuth":
			return astro_satelliteazimuth (satellite, location, nxpass [4])
		if data ==  "time_shift_transit":
			return (nxpass [4] - nxpass [0])
	
def astro_satelliteazimuth (satname, loc, utctime):
	location = astro_obslocation (loc)
	location.date = utctime
	ephobject = astro_pyephsatellite (satname)
	ephobject.compute(location)
	return ('ALT:%4.1f AZ:%5.1f' % (astro_deg (ephobject.alt), astro_deg (ephobject.az))) + " "	+ astro_satellitevisible (satname, loc, utctime)

def astro_satellitevisible (satname, loc, utctime):
	location = astro_obslocation (loc)
	location.date = utctime
	ephobject = astro_pyephsatellite (satname)
	ephobject.compute(location)
	if astro_deg (ephobject.alt) > 20:
		if ephobject.eclipsed:
			return "E"
		else:
			return "V"
	else:
		return "S"


def astro_satelliteMagnitude (satname, loc, utctime):
	# consts
	degrees_per_rad = 180.0 / math.pi
	au = 149597892
	location = astro_obslocation (loc)
	location.date = utctime
	ephobject = astro_pyephsatellite (satname)
	ephobject.compute(location)
	sun = ephem.Sun()
	sun.compute(location)
	iss_std_mag = -1.3
	std_mag = iss_std_mag

	# all times in UTC
	# compare with: https://heavens-above.com/passdetails.aspx?lat=40.7128&lng=-74.0060&loc=Unspecified&alt=0&tz=UCT&satid=25544&mjd=58883.9610767747&type=V

	

	actual_sat_range = (ephobject.range - ephem.earth_radius) / 1000

	a = sun.earth_distance * au # - ephem.earth_radius/1000 - 695510 # Km
	b = ephobject.range / 1000
	angle_c = ephem.separation( (ephobject.az, ephobject.alt), (sun.az, sun.alt) )

	c = math.sqrt(math.pow(a, 2) + math.pow(b, 2) - 2*a*b*math.cos(angle_c))

	phase_angle = math.acos((math.pow(b, 2) + math.pow(c, 2) - math.pow(a, 2)) / (2 * b * c))

	term1 = std_mag
	term2 = 5.0 * math.log10(b / 1000)

	arg = math.sin(phase_angle) + (math.pi - phase_angle) * math.cos(phase_angle)
	term3 = -2.5 * math.log10(arg)

	apparent_mag = term1 + term2 + term3
	return apparent_mag

	

def astro_pyephsatellite (satname):
	
	return ephem.readtle (astro_satTLE (satname)[0],astro_satTLE (satname)[1],astro_satTLE (satname)[2]) 

def astro_satTLE (satellite):

	tlefile = open (tledirectory + "/" + isstelefile, 'r')
	tleline0 = tlefile.readline ()
	tleline1 = tlefile.readline ()
	tleline2 = tlefile.readline ()
	tlefile.close ()
	return ["ISS",tleline1,tleline2]

def astro_moonnextfull (DATETIME=None):

	if DATETIME == None:
		eventdate =ephem.localtime (ephem.next_full_moon(ephem.now()))
		return "FM: " + eventdate.strftime('%b %d %H:%M')
	else:
		return ephem.next_full_moon(DATETIME)

def astro_moonnextnew (DATETIME=None):

	if DATETIME == None:
		eventdate =ephem.localtime (ephem.next_new_moon(ephem.now()))
		return "FM: " + eventdate.strftime('%b %d %H:%M')
	else:
		return ephem.next_new_moon(DATETIME)

		

def astro_moonnphase ():
	location = astro_obslocation ("OULLINS")
	Moon = astro_ephemplanet ("Moon")
	location.date = datetime.datetime.utcnow()
	Moon.compute (location)
	
	return "MOON    %4.0f" % (Moon.moon_phase * 100) + "%   =>"


def astro_obslocation (loc):
	global elevation
	if loc == "OULLINS":
		location = ephem.Observer()
		location.pressure = 0
		location.horizon = '0'
		location.elevation = elevation
		location.lat, location.lon = '45.713809', '4.802196'
	else: 
		location = ephem.Observer()
		location.pressure = 0
		location.horizon = '0'
		location.elevation = 162
		location.lat, location.lon = '45.713809', '4.802196'
	
	return location

def astro_deg (angle_radian):
	return  angle_radian * (180.0 / math.pi)
	


def astro_equinox_solstice (order):
	lstdic = dict ()
	resultat = list ()
	s1 = ephem.next_solstice(ephem.now())
	e1 = ephem.next_equinox(ephem.now())

	lstdic [ephem.localtime (s1).strftime('%Y-%m-%d %H:%M')] = "So" 
	lstdic [ephem.localtime (ephem.next_solstice(s1)).strftime('%Y-%m-%d %H:%M')] = "So" 
	lstdic [ephem.localtime (e1).strftime('%Y-%m-%d %H:%M')] = "Eq" 
	lstdic [ephem.localtime (ephem.next_equinox(e1)).strftime('%Y-%m-%d %H:%M')] = "Eq"

	
	
	alldateslist = lstdic.keys ()
	for eventdate in sorted (lstdic.keys ()):
		resultat.append (lstdic [eventdate] + " :" + eventdate)
		logMsg(lstdic [eventdate] + " :" + eventdate)
	return resultat
 

def astro_eclipses_computing (order):
	location = astro_obslocation ("OULLINS")
	DATETIME=ephem.now()
	
	ephemobj1 = astro_ephemplanet ("Sun")
	ephemobj2 = astro_ephemplanet ("Moon")
	i= 0
	while i < order:
		
		DATETIME = astro_moonnextfull (DATETIME)
		location.date = DATETIME
		ephemobj1.compute (location)
		ephemobj2.compute (location)

		
		rT = ephem.earth_radius
		rS = ephem.sun_radius 
		rL = ephem.moon_radius 


		dLT = ephemobj2.earth_distance * ephem.meters_per_au #distance terre lune en metres

		dTS = ephemobj1.earth_distance * ephem.meters_per_au #distance terre soleil en metres
		
		dLS = ephemobj2.sun_distance * ephem.meters_per_au #distance terre soleil en metres

		LCONE =  (dTS * rT) / (rS - rT)
		rOMBRE = rT - (dLT * ((rS - rT) / (dLS - dLT)))
		aOMBRE = math.atan (rOMBRE / dLT)
	
		angleLimite =astro_deg  (aOMBRE + ephemobj2.radius)
		angleLimiteTotale = astro_deg  (aOMBRE - ephemobj2.radius)
		sep = astro_deg (ephem.separation(( ephemobj1.a_ra , ephemobj1.a_dec ), ( ephemobj2.a_ra,ephemobj2.a_dec))) 
		if 180 - sep < angleLimite :
			i = i +1
			
			if 180 - sep < angleLimiteTotale :
				logMsg ("====== Eclipse totale : " + str (DATETIME))
			else:
				logMsg ("====== Eclipse partielle : " + str (DATETIME))
			logMsg ("***** Date : " + str (DATETIME))
			logMsg ("Separation Lune / Soleil " + str (sep))
			logMsg ("Angle limite eclipse : " + str (angleLimite))
			logMsg ("Demi Taille lune :" + str (astro_deg (ephemobj2.radius)))
			logMsg ("Demi Taille ombre en degres   :" + str (astro_deg (aOMBRE)))


	return  ephem.localtime (DATETIME).strftime('%Y-%m-%d %H:%M')

def astro_sun_eclipses_computing (order):
	location = astro_obslocation ("OULLINS")
	DATETIME=ephem.now()
	
	Sun  = astro_ephemplanet ("Sun")
	Moon = astro_ephemplanet ("Moon")
	i= 0
	while i < order:
		
		DATETIME = astro_moonnextnew (DATETIME)
		location.date = DATETIME
		Sun.compute (location)
		Moon.compute (location)

		
		rT = ephem.earth_radius
		rS = ephem.sun_radius 
		rL = ephem.moon_radius 
		dLT = Moon.earth_distance * ephem.meters_per_au #distance terre lune en metres
		dTS = Sun.earth_distance * ephem.meters_per_au #distance terre soleil en metres
		dLS = Moon.sun_distance * ephem.meters_per_au #distance terre soleil en metres

		LCONE =  (dTS * rT) / (rS - rT)
		rOMBRE = rT - (dLT * ((rS - rT) / (dLS - dLT)))
		aOMBRE = math.atan (rOMBRE / dLT)
	
		angleLimite =astro_deg  (aOMBRE + Moon.radius)
		angleLimiteTotale = astro_deg  (aOMBRE - Moon.radius)
		angleLimite = 0.5
		angleLimiteTotale = 0.25


		sep = astro_deg (ephem.separation(( Sun.ra, Sun.dec ), ( Moon.ra,Moon.dec))) 
		if sep < angleLimite :
			i = i +1
			
			if 180 - sep < angleLimiteTotale :
				logMsg ("====== Eclipse totale : " + str (DATETIME))
			else:
				logMsg ("====== Eclipse partielle : " + str (DATETIME))
			logMsg ("***** Date : " + str (DATETIME))
			logMsg ("Separation Lune / Soleil " + str (sep))
			logMsg ("Angle limite eclipse : " + str (angleLimite))
			logMsg ("Demi Taille lune :" + str (astro_deg (Moon.radius)))
			logMsg ("Demi Taille ombre en degres   :" + str (astro_deg (aOMBRE)))


	return  ephem.localtime (DATETIME).strftime('%Y-%m-%d %H:%M')

def astro_events_management ():
	global scheduler
	#followedObjects = ["ISS","Jupiter","Moon","Sun","Mercure","Venus","Saturn","Mars"]
	followedObjects = ["Jupiter","Moon","Sun","Mercure","Venus","Saturn","Mars","ISS"]
	logMsg ("-----Start computing astro events")
	for astroObj in followedObjects:
		logMsg ("Astro events for rising :" + astroObj )
		#scheduler.logMsg_jobs()
		jobname = astroObj + "RISE"

		if scheduler.get_job(jobname):
				logMsg ("Removing old schedule for " + jobname)
				scheduler.remove_job(jobname)
		
		if astroObj == "ISS":
			rise_time = astro_satellitenextpass (astroObj,"rise_time",utc=True)
			
			nbbeeps = 60
			timetowait = 600

		else :
			
			rise_time = astro_planetnextrising (astroObj,utc=True)
			nbbeeps = 3
			timetowait = 60 

		logMsg ("Adding schedule for " + jobname + " at " + rise_time)			 
		scheduler.add_job(astro_rising_events,'date', run_date=rise_time,id=jobname,args =(astroObj,nbbeeps,timetowait))
		
		#scheduler.logMsg_jobs()
		
	scheduler.print_jobs()
	logMsg ("-----Stop computing astro events")		

def astro_rising_events (objectname,nbbeeps,timetowait):
	global screenbusy
	logMsg ("Rising object event :" + objectname)
	if not screenbusy:
		screenbusy = True
		delay (1000)
		logMsg ("Start beep trigger")
		tbeep = threading.Thread (target = beep, args=(nbbeeps,50,25, 10))
		tbeep.start ()

		if objectname == "ISS":
			logMsg ("Start beep trigger 2 for ISS")
			tbeep2 = threading.Thread (target = beep, args=(40,20,15000,10,30000))
			tbeep2.start ()	
		
		logMsg ("Start object screen__" + objectname.lower () +"  timetowait : " + str(timetowait))
		screen_general2 (screenslist ["screen__"+ objectname.lower ()] ,timetowait, lck = True)
		
		screenbusy = False



def downloadfile (src, tgtdir,tgtfile):

	try :
		dl_fichier= wget.download(src, tgtdir)
	except: 
		logMsg ("Erreur chargement fichier TLE : " + src + "vers : " + tgtdir )

		pass
	
	logMsg ("file downloaded : " + str (dl_fichier))
	if os.path.isfile(str (dl_fichier)):
		
		if os.path.isfile(tgtdir + "/" + tgtfile):
			os.remove (tgtdir + "/" + tgtfile)
		os.rename (dl_fichier,tgtdir + "/" + tgtfile)

	return




def getNodes (nodes,nodeID):
	for nodeNum in nodes:
		if nodes[nodeNum]["ID"] == nodeID:
			return nodeNum
	return None





#fonctions a declarer au depart
def shutdown_now ():
	os.system('sudo shutdown -h now')

def reboot_now ():
	os.system('sudo shutdown -r now')

def delay(ms):
	time.sleep(1.0*ms/1000)


# Texte et actions pour les ecrans

def screen_list ():
	result = dict ()
	Base = automap_base()

	# engine, suppose it has two tables 'user' and 'address' set up
	db = create_engine("sqlite:///" + dbname)

	# reflect the tables
	Base.prepare(db, reflect=True)
	screens = Base.classes.screens
	# mapped classes are now created with names by default
	# matching that of the table name.

	session = Session(db)
	
	for row in session.query(screens).all():
		result [row.NAME] = row
	
	session.close()
	return result
	

## Fonctions


def rf_readparam(line):
	global node
	paramslist=line.split (";")
	paramdico = {}

	paramdico["RXTX"] = "#NA"
	paramdico["TXID"] ="#NA"
	paramdico["DEVICETYPE"] = "#NA"
	paramdico["ID"] = "#NA"
	if len(paramslist)>2:
		paramdico["RXTX"] = paramslist [0]
		paramdico["TXID"] = paramslist [1]
		paramdico["DEVICETYPE"] = paramslist [2]
	
		for i in range (3,len (paramslist)):
			paramlist=paramslist[i].split ("=")
			if len (paramlist) == 2:	
				paramdico[paramlist[0]] = paramlist[1]
		nodeNum = getNodes (node,paramdico["ID"])
		if nodeNum:
			if node[nodeNum].get("TEMPFormat"):
				paramdico = meteo_tempformat (paramdico,node[nodeNum].get("TEMPFormat"))
	return paramdico

def meteo_hexatodectemp (temperaturehexa):
	if len(temperaturehexa) != 4:
		return hexatodectemp
	
	dectemp=int(temperaturehexa [1:4],16) / 10.0
	
	if  (temperaturehexa [0:1] != "0"):
		dectemp = -1 * dectemp
	
	return dectemp

def meteo_tempformat (params,TEMPFormat):
	if TEMPFormat=='oregon':
		params ["TEMP"]= meteo_hexatodectemp (params ["TEMP"])
	return params


#Initialisation de l'ecran
def lcd_init (light=1):
	lcd = I2C_LCD_driver.lcd()
	lcd.lcd_clear
	lcd.backlight(light)

	return lcd


def lcd_echo (lcd,msgligne1,msgligne2,msgligne3,msgligne4):

	spaceline = "                    "   
	if msgligne1 == None:
		msgligne1 =""
	if msgligne2 == None:
		msgligne2 =""
	if msgligne3 == None:
		msgligne3=""
	if msgligne4 == None:
		msgligne4=""
	
	
	allline = {	1:msgligne1,2:msgligne2,3:msgligne3,4:msgligne4}
	
	for iline in sorted (allline):
		
		if len (allline[iline]) > 4:
			if (allline[iline])[:4]=="CMD=" :
				allline[iline] = eval (allline[iline] [4:]) ()

		allline[iline] = (allline[iline] + spaceline) [:20]
		if not sleeping2:
			lcd.lcd_display_string(allline[iline], iline)

	#tkline1,tkline2,tkline3,tkline3
	#tkline1.set (allline[1])
	#tkline2.set (allline[2])
	#tkline3.set (allline[3])
	#tkline4.set (allline[4])

        
def lcd_clear (lcd):
	msgligne ="                    "
	lcd.lcd_display_string(msgligne, 1)
	lcd.lcd_display_string(msgligne, 2)
	lcd.lcd_display_string(msgligne, 3)
	lcd.lcd_display_string(msgligne, 4)


		

def log_database():
	global node,client
	global mqtt_brocker,topic
	global dbname,measureList
	while (1):
		delay (300000)
		

	# disable node[1]
#		node[1]["TEMP"]=0
		#node[1]["HUM"]=0


#		conn=sqlite3.connect(dbname)
#		curs=conn.cursor()
#		curs.execute("INSERT INTO envtb(ts,node0TEMP,node0PRESSURE,node1TEMP,node1HUM) VALUES(?,?,?,?,?)",(node[0]["TIMESTAMP"],node[0]["TEMP"],node[0]["PRESSURE"],node[1]["TEMP"],node[1]["HUM"]))
#		conn.commit()
#		conn.close()


		for nodeNum in node:
			if node[nodeNum]["CATEGORY"]=="PROBE":
				if node[nodeNum].get("TIMESTAMP"):
					if node[nodeNum]["TIMESTAMP"] != None:
						if datetime.datetime.utcnow() - node[nodeNum]["TIMESTAMP"] >  datetime.timedelta(seconds=900):
							for measure in measureList:
								if node[nodeNum].get(measure):
									node[nodeNum][measure]=None
				jsonDic={'deviceid' : node[nodeNum]["deviceid"]}
				for measure in measureList:
					if node[nodeNum].get(measure):
						jsonDic[measure]=node[nodeNum][measure]
				json_msg=json.dumps(jsonDic)

		# encoded_message = json.dumps(json_message).encode('utf8')
				logMsg ("Sending data  to Brocker  :  " + str(json_msg))
				logMsg (mqtt_brocker + "    -    " + topic)
				send_msg (mqtt_brocker,topic,str(json_msg))


def interruption0 ():
	global inter_state0
	logMsg ("Interruption0")
	inter_state0 = True

def interruption1(test):
	global inter_state1,sleeping2
	logMsg ("Interruption1")
	touchdata= cap.touched()
	if touchdata != 0 :
		logMsg (str(touchdata))
		inter_state1 = touchdata
	beep (1,100,0,128)
	sleeping2 = False

	
def rflink():
	global curtemp2, curhumidity2,probe1,txcmd,infoscreen,infoscreen_enable,measureList
	with serial.Serial('/dev/ttyACM0', 57600, timeout=1,bytesize=serial.EIGHTBITS,parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE) as ser:
	#with serial.Serial('/dev/ttyAMA0', 57600, timeout=1,bytesize=serial.EIGHTBITS,parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE) as ser:
		ser.rts = True
		line = ser.readline()	   # read a '\n' terminated line

		while (1):
			
			line = ser.readline()	   # read a '\n' terminated line
			line = line.decode('utf-8')
			if (line != ""):
	
				logMsg (line)
				dicoparams = rf_readparam (line)
			# cas node[1]

				nodeNum=getNodes (node,dicoparams["ID"])
				if nodeNum:
					for measure in measureList:
						if dicoparams.get(measure):
							node[nodeNum][measure]= dicoparams[measure]
							node[nodeNum]["TIMESTAMP"]=datetime.datetime.utcnow()
							logMsg (node[nodeNum]["TIMESTAMP"].strftime('%b %d %H:%M:%S') +" " + measure + " " + node[nodeNum]["LOCATION"] + " : " + str(node[nodeNum][measure]))



			# cas node[4] (Remote control
			# cas node[4] (Remote control
				if dicoparams["ID"] == node[4]["ID"]:
					if dicoparams["SWITCH"] == node[4]["SWITCH"] and dicoparams["CMD"] == node[4]["CMD"]:
						infoscreen_enable = True
						infoscreen =  screen__allplugs_result 
						txcmd.append (node[2]["CMDON"] + node[3]["CMDON"])
			delay (100)
			for cmd in txcmd:
				ser.write (cmd)
				txcmd.remove (cmd) 
				delay (100)
				

def mesure():
	global curtemp1,node
	while(1):
		mesurelist =[]
		for i in range (0,1000):
			mesurelist.append (analog_read(temperature_pin))
			delay (10)
		value=sum(mesurelist) / float(len(mesurelist))
		volts=(value*3.0)/4095
		temperature_C =((volts - 0.5)*100) - 1.2
		curtemp1 = "%4.1f" % temperature_C
		curvoltage1="volts = %5.3f V" % volts
		node[0]["TEMP"]="%4.1f" % temperature_C
		node[0]["TIMESTAMP"]=datetime.datetime.utcnow()

		#curtemp1 = node[0]["TEMP"]
		logMsg (node[0]["TIMESTAMP"].strftime('%b %d %H:%M:%S') + "   Temperature " + node[0]["LOCATION"] + " : " + node[0]["TEMP"]) 
		delay (15000)


def mesure_bmp380():
	global curtemp1,node

	while (1):
		node[0]["TEMP"],node[0]["PRESSURE"],vide = bme280.readBME280All()
		if node[0]["PRESSURE"] != None:
			# correction en altitude
			node[0]["PRESSURE"]=node[0]["PRESSURE"] + (pressureelevation * elevation)

		node[0]["TEMP"]="%4.1f" % node[0]["TEMP"]
		node[0]["PRESSURE"]="%4.1f" % node[0]["PRESSURE"]
		
		
		node[0]["TIMESTAMP"]=datetime.datetime.utcnow()
		curtemp1 = node[0]["TEMP"]
		#print (node[0]["TIMESTAMP"].strftime('%b %d %H:%M:%S') + "   Temperature " + node[0]["LOCATION"] + " : " + node[0]["TEMP"]) 
		#print (node[0]["TIMESTAMP"].strftime('%b %d %H:%M:%S') + "   Pression " + node[0]["LOCATION"] + " : " + node[0]["PRESSURE"]) 
		curtemp1 = node[0]["TEMP"]
		delay (15000)


# gestion des ecrans ...............
	
def screen_main():
	global node
	lcd_echo (lcd,datetime.datetime.now().strftime('%b %d %H:%M:%S'),"Int T:" + str(node[0]["TEMP"])+ " P:"+ str(node[0]["PRESSURE"]),"T balcon :" + str(node[1]["TEMP"]),"HUM balcon :" + str(node[5]["HUM"])+"%")



def screen_menu (menu):
	global lcd,screenslist
	exitloop = False
	pointermenu = 1
	maxindex = len (menu)
	screen_result = "DOWN"
	
	while not exitloop:
		
		screen_result = screen_general2 (menu [pointermenu],5)
		if screen_result == "DOWN":
			pointermenu = pointermenu + 1
			if pointermenu == maxindex + 1:
				pointermenu = 1

		elif screen_result == "UP":
			pointermenu = pointermenu - 1 
			if pointermenu == 0:
				pointermenu = maxindex


		elif (screen_result == "RIGHT" or screen_result== "OK") and  menu [pointermenu].ISDIRECTORY :
				
				MNLIST = dict ()
				MNLIST = eval (menu [pointermenu].DIRECTORYCHILDS)
				screen_menu (MNLIST)
			
	
		elif screen_result == "LEFT":
			exitloop = True
		
		elif screen_result == "LOCK":
			exitloop = True
		
		else :
			exitloop = True	




def screen_general2 (dicscreen,timetowait,lck = False):
	global inter_state0,inter_state1,keypad,lcd,sleeping2
	inter_state0 = False
	inter_state1 = 0
	status_lck=lck
	if not sleeping2:
		lcd_clear (lcd)
	
	allline = {	1:dicscreen.LINE1,2:dicscreen.LINE2,3:dicscreen.LINE3,4:dicscreen.LINE4}
	lcd_echo (lcd,allline [1],allline [2],allline [3],allline[4])
	

	start_time=time.time()
	
	t_end = time.time() + timetowait
	logMsg ("Displaying screenGeneral2 for : " + str(timetowait) + " s" )
	
	while time.time() < t_end:
		
		delay(50)
		
		if (lck and inter_state1 != 0):
			return ""
		
		if( inter_state1== keypad["button_ok"]): 	
			if dicscreen.HASCHLD:
				if dicscreen.CMDENABLE:
					rs = eval (dicscreen.CMD)

				if dicscreen.CMDRFLINKENABLE:
					txcmd.append (eval(dicscreen.CMDRFLINK))
				screen_general2 (eval (dicscreen.RESULTSCREEN),5)	
				return 0
			else:
				inter_state0 = False
				inter_state1 = 0
				return "RIGHT"

		if(inter_state1 == keypad["button_down"]):	
			inter_state0 = False
			inter_state1 = 0
			return "DOWN"
		if(inter_state1 == keypad["button_up"]):	
			inter_state0 = False
			inter_state1 = 0
			return "UP"
		if(inter_state1 == keypad["button_left"]):	
			inter_state0 = False
			inter_state1 = 0
			return "LEFT"
		if(inter_state1 == keypad["button_right"]):	
			inter_state0 = False
			inter_state1 = 0
			return "RIGHT"
		if(inter_state1 == keypad["button_lock"] or status_lck):	
			logMsg ("Locking menu")
			if status_lck:
				timetowait2 = timetowait
			else:
				timetowait2 = 1800
			inter_state1 = 0
			lcd_echo (lcd,"Screen locked       ","                    ","                    ","                    ")
			delay (1000)
			t_end2 = time.time() + timetowait2
			while (time.time() < t_end2) and inter_state1 == 0:
				lcd_echo (lcd,allline [1],allline [2],allline [3],allline[4])
				delay (1000)
			status_lck = False
			inter_state1 = 0
			inter_state0 = False
			return ""
	logMsg ("End Displaying screengeneral2")
	inter_state1 == 0
	lcd_clear (lcd)
	return ""

def interruption1_set (x):
	global inter_state1
	inter_state1 = x
	logMsg (x)

def screen_mirror_window ():
	global tkline1,tkline2,tkline3,tkline4
	fenetre = Tk()
	tkline1=StringVar ()
	tkline2=StringVar ()
	tkline3=StringVar ()
	tkline4=StringVar ()
	

	Label(fenetre, textvariable=tkline1).grid(row=0,columnspan=3, sticky=W)
	Label(fenetre, textvariable=tkline2).grid(row=1,columnspan=3, sticky=W)
	Label(fenetre, textvariable=tkline3).grid(row=2,columnspan=3, sticky=W)
	Label(fenetre, textvariable=tkline4).grid(row=3,columnspan=3, sticky=W)
	Canvas(fenetre, width=250, height=100, bg='ivory')
	Button(fenetre, text='', borderwidth=1,command=lambda : interruption1_set(keypad["button_down"])).grid(row=4, column=1)
	Button(fenetre, text='UP',borderwidth=1,command=lambda : interruption1_set(keypad["button_up"])).grid(row=4, column=2)
	Button(fenetre, text='lk',borderwidth=1,command=lambda : interruption1_set(keypad["button_lock"])).grid(row=4, column=3)
	Button(fenetre, text='LE',borderwidth=1,command=lambda : interruption1_set(keypad["button_left"])).grid(row=5, column=1)
	Button(fenetre, text='OK',borderwidth=1,command=lambda : interruption1_set(keypad["button_ok"])).grid(row=5, column=2)
	Button(fenetre, text='RI',borderwidth=1,command=lambda : interruption1_set(keypad["button_right"])).grid(row=5, column=3)
	Button(fenetre, text='',borderwidth=1).grid(row=6, column=1)
	Button(fenetre, text='DO',borderwidth=1,command=lambda : interruption1_set(keypad["button_down"])).grid(row=6, column=2)
	Button(fenetre, text='',borderwidth=1,command=lambda : interruption1_set(keypad["button_down"])).grid(row=6, column=3)
	Button(fenetre, text='L1',borderwidth=1,command=lambda : interruption1_set(keypad["button_down"])).grid(row=7, column=1)
	Button(fenetre, text='L2',borderwidth=1,command=lambda : interruption1_set(keypad["button_down"])).grid(row=7, column=2)
	Button(fenetre, text='L3',borderwidth=1,command=lambda : interruption1_set(keypad["button_down"])).grid(row=7, column=3)
		

	fenetre.update_idletasks()
	
	fenetre.mainloop()


# eploitation des donnees en base
def meteo_GetExtrema (colonne,ExtremaType,deltadays):


	jalondate=datetime.datetime.now() - datetime.timedelta(days=deltadays)
	conn=sqlite3.connect(dbname)
	 

	curs=conn.cursor()

	cmd="SELECT %s(%s) FROM envtb WHERE ts >'%s'" %(ExtremaType,colonne,jalondate)
	result =curs.execute(cmd)
	extrema =  curs.fetchone()
	cmd="SELECT ts,%s FROM envtb WHERE (%s = '%s' and ts > '%s' )" %(colonne, colonne, extrema[0],jalondate)
	

	result =curs.execute(cmd)
	row = curs.fetchone()
	utcdate = datetime.datetime.strptime(row[0],'%Y-%m-%d %H:%M:%S.%f')
	value = row [1]
	#row[0] = objdate.strftime ('%Y %m %d %H:%M')
	conn.close()
	return [utcdate,value]


#Telechargement du fichier TLE
def downloadtle ():
	logMsg ("Loading TLE File" + isstelefile)
	try:
		downloadfile (isstleurl,tledirectory,isstelefile)
	except:
		logMsg ("ERR :Loading TLE File" + isstelefile)
		pass
	



# gestion des Beeps

def beep (nb_beeps,duree,interval,volume,timetowait = 1 ):
	global buzzer_pin
	global sleeping2
	
	
	if not sleeping2:
		delay (timetowait)
		i=nb_beeps
		for i in range (nb_beeps ):
			delay (100)
			GPIO.output (buzzer_pin, 1)
			delay (duree)
			GPIO.output (buzzer_pin, 0)
			delay (interval)


  
def jobs_management ():
	global scheduler
	scheduler.start()
	# gestion des evenements astro - recalcul toutes les heures

	if scheduler.get_job('astro_events_management'):
		scheduler.remove_job('astro_events_management')
	scheduler.add_job(astro_events_management, 'interval', minutes=60, id='astro_events_management')
	
	if scheduler.get_job('downloadtle'):
		scheduler.remove_job('downloadtle')
	scheduler.add_job(downloadtle, 'interval', hours=24, id='downloadtle')
	
	
	
	scheduler.print_jobs()
	# lance le job de calcul astro
	astro_events_management ()

#  Functions

def send_msg (mqtt_brocker,topic,json_msg):
	try:
		logMsg ("Sending json Message to broker")
		client = mqtt.Client()
		client.connect(mqtt_brocker,1883,60)
		client.publish(topic, str (json_msg));
		client.disconnect();
	except:
		logMsg ("ERR: Sending json Message to broker")
		pass





logMsg ("LCD INIT")
lcd=lcd_init (1)

#noInterrupts()
#attachInterrupt(0,interruption0,FALLING)
#attachInterrupt(1,interruption1,FALLING)
#interrupts()

logMsg ("Creating threads")
t6 = threading.Thread (target = mesure_bmp380)
t4 = threading.Thread (target = log_database)
t3 = threading.Thread (target = rflink)

#t2 = threading.Thread (target = mesure)
#t1 = threading.Thread (target = led_blinking)
#t0 = threading.Thread (target = screen_mirror_window)
logMsg ("Starting threads")
#t0.start()
#t1.start()
#t2.start()
t3.start()
t4.start()
t6.start()

# downloading TLE for IIS
downloadtle ()

inter_state0 = False
inter_state1 = 0

infoscreen_enable = False
infoscreen=dict()

logMsg ("Keyboard initialization")
#Initialisation clavier mpr121
cap = MPR121.MPR121()
if not cap.begin():
    logMsg('Failed to initialize MPR121, check your wiring!')
    sys.exit(1)


GPIO.setup(gpioKeyboard, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.add_event_detect(gpioKeyboard, GPIO.FALLING, interruption1)
atexit.register(GPIO.cleanup)

# Clear any pending interrupts by reading touch state.
cap.touched()

# generate screens from database
logMsg ("Generating screen list from database")
screenslist = screen_list ()


# enregistrement de la liste des ecrans

menuroot = {1:screenslist["screen__folder_lights"],2:screenslist["screen__folder_ephemeride"],3:screenslist["screen__folder_meteo"],4:screenslist["screen__folder_System"]}




# lancement des jobs
logMsg ("Starting Scheduler management")
jobs_management ()

#astro_equinox_solstice ()


sleeping2 = False

logMsg ("Testing Buzzer")
beep (5,100,0,128)


screenbusy = False
while (1):
	if not screenbusy:
		screen_main ()
		#affichage des evenements en temps reel
		if infoscreen_enable:
			screen_general2 (infoscreen,1) 
			infoscreen_enable=False
			
		
		if inter_state1==8 :
			infoscreen_enable = True
			infoscreen =  screenslist ["screen__plug1_result"] 
			txcmd.append (node[3]["CMDON"])
			inter_state1 = 0
		if inter_state1==128 :
			infoscreen_enable = True
			infoscreen =  screenslist ["screen__plug2_result"] 
			txcmd.append (node[2]["CMDON"])
			inter_state1 = 0
		if inter_state1==2048 :
			infoscreen_enable = True
			infoscreen =  screenslist ["screen__allplugs_result"] 
			txcmd.append (node[2]["CMDON"] + node[3]["CMDON"])
			inter_state1 = 0

		if inter_state1== keypad["button_sleep"] :
			if sleeping2:
				sleeping2 = False
				inter_state1 = 0
			else:
				sleeping2 = True
				inter_state1 = 0
				lcd=lcd_init (0)
				
	delay (50)


# Demarrage de l'affichage des menus

	if  inter_state1 == keypad["button_down"]:
		lcd=lcd_init ()
		inter_state1 = 0
		
		screen_menu (menuroot)
	






