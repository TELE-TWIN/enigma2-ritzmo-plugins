# To check if in Standby
import Screens.Standby

# Timer, eServiceReference
from enigma import eTimer, eServiceReference

# Check if in timespan, calculate timer durations
from time import localtime, mktime, time

# Path (check if file exists, getmtime)
from os import path

# We want a list of unique services
from sets import Set

# Configuration
from Components.config import config

# Path to configuration
CONFIG = "/etc/enigma2/epgrefresh.conf"

class EPGRefresh:
	"""WIP - Simple Class to refresh EPGData - WIP"""

	def __init__(self):
		# Initialize Timer
		self.timer = eTimer()
		self.timer.timeout.get().append(self.timeout)

		# Initialize 
		self.services = Set()
		self.previousService = None
		self.timer_mode = 0

		# Mtime of configuration files
		self.configMtime = -1

		# Read in Configuration
		self.readConfiguration()

	def readConfiguration(self):
		# Check if file exists
		if not path.exists(CONFIG):
			return

		# Check if file did not change
		mtime = path.getmtime(CONFIG)
		if mtime == self.configMtime:
			return

		# Keep mtime
		self.configMtime = mtime

		# Empty out list
		self.services.clear()

		# Open file
		file = open(CONFIG, 'r')

		# Add References
		for line in file:
			self.services.add(line)

		# Close file
		file.close()

	def saveConfiguration(self):
		# Open file
		file = open(CONFIG, 'w')

		# Write references
		for serviceref in self.services:
			file.write(serviceref)

		# Close file
		file.close()

	def refresh(self):
		print "[EPGRefresh] Forcing start of EPGRefresh"
		self.timer_mode = 2
		self.timeout()

	def start(self):
		# Calculate unix timestamp of begin of timespan
		begin = [x for x in localtime()]
		begin[3] = config.plugins.epgrefresh.begin.value[0]
		begin[4] = config.plugins.epgrefresh.begin.value[1]
		begin = mktime(begin)

		# Calculate difference
		delay = begin-time()

		# Wait at least 3 seconds
		if delay < 3:
			delay = 3

		# debug, start timer
		print '[EPGRefresh] Timer will fire for the first time in %d seconds' % (delay) 
		self.timer.startLongTimer(int(delay))

	def stop(self):
		print "[EPGRefresh] Stopping Timer"
		self.timer.stop()
		self.timer_mode = 0

	def checkTimespan(self, begin, end):
		# Get current time
		time = localtime()

		# Check if we span a day
		if begin[0] > end[0] or (begin[0] == end[0] and begin[1] >= end[1]):
			# Check if begin of event is later than our timespan starts
			if time[3] > begin[0] or (time[3] == begin[0] and time[4] >= begin[1]):
				# If so, event is in our timespan
				return True
			# Check if begin of event is earlier than our timespan end
			if time[3] < end[0] or (time[3] == end[0] and time[4] <= end[1]):
				# If so, event is in our timespan
				return True
			return False
		else:
			# Check if event begins earlier than our timespan starts 
			if time[3] < begin[0] or (time[3] == begin[0] and time[4] <= begin[1]):
				# Its out of our timespan then
				return False
			# Check if event begins later than our timespan ends
			if time[3] > end[0] or (time[3] == end[0] and time[4] >= end[1]):
				# Its out of our timespan then
				return False
			return True

	def timeout(self):
		# Walk Services
		if self.timer_mode == 3:
			self.nextService()

		# Pending for activation
		elif self.timer_mode == 0:
			# Check if in timespan
			if self.checkTimespan(config.plugins.epgrefresh.begin.value, config.plugins.epgrefresh.end.value):
				self.timer_mode = 1
				self.timeout()
			else:
				print "[EPGRefresh] Not in timespan, rescheduling"
				# Recheck in 1h
				self.timer.startLongTimer(3600)

		# Check if in Standby
		elif self.timer_mode == 1:
			# Do we realy want to check nav?
			from NavigationInstance import instance as nav
			if Screens.Standby.inStandby and not nav.RecordTimer.isRecording():
				self.timer_mode = 2
				self.timeout()
			else:
				# See if we're still in timespan
				if self.checkTimespan(config.plugins.epgrefresh.begin.value, config.plugins.epgrefresh.end.value):
					print "[EPGRefresh] Box still in use, rescheduling"	

					# Recheck in 10min
					self.timer.startLongTimer(600)
				else:
					print "[EPGRefresh] Gone out of timespan while waiting for box to be available, sorry!"

					# Clean up
					self.timer_mode = 4
					self.timeout()

		# Reset Values
		elif self.timer_mode == 2:
			print "[EPGRefresh] About to start refreshing EPG"
			# Keep service
			from NavigationInstance import instance as nav
			self.previousService =  nav.getCurrentlyPlayingServiceReference()

			# Maybe read in configuration
			try:
				self.readConfiguration()
			except Exception, e:
				print "[EPGRefresh] Error occured while reading in configuration:", e

			# Make a copy of services as we're going to modify the list
			self.scanServices = self.services.copy()

			# See if we are supposed to read in autotimer services
			if config.plugins.epgrefresh.inherit_autotimer.value:
				try:
					# Import Instance
					from Plugins.Extensions.AutoTimer.plugin import autotimer

					# See if instance is empty
					if autotimer is None:
						# Create a dummy instance
						from Plugins.Extensions.AutoTimer.AutoTimer import AutoTimer
						autotimer = AutoTimer(None)

						# Read in configuration
						autotimer.readXml()

						# Get enabled timers
						list = autotimer.getEnabledTimerList()

						# Remove dummy instance
						autotimer = None
					else:
						# TODO: force parsing?
						# Get enabled timers
						list = autotimer.getEnabledTimerList()

					# Fetch services
					for timer in list:
						self.scanServices = self.scanServices.union(Set(timer.getServices()))
				except Exception, e:
					print "[EPGRefresh] Could not inherit AutoTimer Services:", e

			# Debug
			print "[EPGRefresh] Services we're going to scan:", self.scanServices

			self.timer_mode = 3
			self.timeout()

		# Play old service, restart timer
		elif self.timer_mode == 4:
			# Reset mode
			self.timer_mode = 0

			# Zap back
			from NavigationInstance import instance as nav
			nav.playService(self.previousService)

			# Calculate delay until in timespan again
			# What we do is the following:
			#  We calculate the last end time and add 24h
			#  Then we change h/m to begin time
			#  That way we should always get the next begin
			begin = [x for x in localtime()]
			begin[3] = config.plugins.epgrefresh.end.value[0]
			begin[4] = config.plugins.epgrefresh.end.value[1]
			begin = mktime(begin)+86400

			begin = [x for x in localtime(begin)]
			begin[3] = config.plugins.epgrefresh.begin.value[0]
			begin[4] = config.plugins.epgrefresh.begin.value[1]
			begin = mktime(begin)

			# Calculate difference
			delay = begin-time()

			# Wait at least 3 seconds (ok, this should never happen :))
			if delay < 3:
				delay = 3

			# debug, start timer
			print '[EPGRefresh] Timer will fire again in %d seconds' % (delay) 
			self.timer.startLongTimer(int(delay))

		# Corrupted ?!
		else:
			print "[EPGRefresh] Invalid status reached:", self.timer_mode
			self.timer_mode = 1
			self.timeout()

	def nextService(self):
		# DEBUG
		print "[EPGRefresh] Maybe zap to next service"

		# Check if more Services present
		if len(self.scanServices):
			# Get next reference
			serviceref = self.scanServices.pop()

			# Play next service
			from NavigationInstance import instance as nav
			nav.playService(eServiceReference(str(serviceref)))

			# Start Timer
			self.timer.startLongTimer(config.plugins.epgrefresh.interval.value*60)
		else:
			# Debug
			print "[EPGRefresh] Done refreshing EPG"

			# Clean up
			self.timer_mode = 4
			self.timeout()

epgrefresh = EPGRefresh()