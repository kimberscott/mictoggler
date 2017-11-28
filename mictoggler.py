# MicToggler
# (c) 2015 Steven Scott

import random
import datetime
import time
import os.path
import threading
import inspect
import subprocess as sp
import wx
import wx.lib.masked
import sys
import threading

class StepDistribution:
	'''Class for creating and storing a distribution of on/off steps'''
	path = 'D:/mictoggler/' # Only used for command-line version
	datapath = os.path.join(path, 'data')
	listStartMarker = 'STEPLIST\r\n'
	nInstances = 0;
	
	def __init__(self, paramsOrFile):
		'''Create a new StepDistribution object with Gaussian-distributed on/off times
		
		if parameters are given, paramsOrFile should be a dictionary with these fields:
		nSteps: number of (on/off) steps to create
		fracOn: what fraction of the STEPS should be on
		avgDurOn: mean (s) for the Gaussian distribution used to generate ON steps
		stdDurOn: standard deviation (s) for the Gaussian distribution used for ON steps
		minDurOn: minimum duration (s) of ON steps
		maxDurOn: maximum duration (s) of ON steps
		avgDurOff: mean (s) for the Gaussian distribution used to generate OFF steps
		stdDurOff: standard deviation (s) for the Gaussian distribution used for OFF steps
		minDurOff: minimum duration (s) of OFF steps
		maxDurOff: maximum duration (s) of OFF steps
		
		This initializes the values of the parameters used for generating the list of 
		steps but does NOT itself generate a distribution.
		
		if paramsOrFile is a filename it should be a string giving the full path to a saved
		distribution file.
		
		After initialization and creation of a distribution, params will contain the 
		above parameters and also three statistical summary parameters: fracTimeOn, 
		fracStepsOn, and timeTotal.  These refer to the actual distribution generated and
		not the parameters used to generate it.'''
		
		if type(paramsOrFile) == type({}):
			self.params = paramsOrFile
			# Convert fields to floats
			expectedFields = ['nSteps', 'fracOn', 'avgDurOn', 'stdDurOn', 'minDurOn', 
				  'maxDurOn', 'avgDurOff', 'stdDurOff', 'minDurOff', 'maxDurOff']
			for eF in expectedFields:
				self.params[eF] += 0.0
			# Require all delays nonnegative
			self.params['minDurOn'] = max(self.params['minDurOn'], 0.0)
			self.params['maxDurOn'] = max(self.params['maxDurOn'], 0.0)
			self.params['minDurOff'] = max(self.params['minDurOff'], 0.0)
			self.params['maxDurOff'] = max(self.params['maxDurOff'], 0.0)
			self.__set_seq()
		elif type(paramsOrFile) == type('str'):
			self.load_file(paramsOrFile)
		
		StepDistribution.nInstances += 1 # used only for file naming to avoid overwriting
		
	def load_file(self, filepath):
		'''Loads a text distribution file (parameters and actual distribution) created earlier.
		
		Expects the full path to a .txt file with a header section that defines all of the 
		variables accepted by __init__ and a body with the actual list of on/off steps, each
		on its own line and represented as OnOff[boolean], Duration[float]'''
		stillInHeader = True
		stepList = []
		self.params = {}
		with open(filepath, 'r') as f:
			for line in f:
				if stillInHeader:
					if '=' in line:
						self.read_var(line)
						
					if line.strip() == self.listStartMarker.strip():
						stillInHeader = False
				else:
					vals = line.strip().split(',')
					tup = (vals[0]=='True', float(vals[1]))
					stepList.append(tup)
					
		self.stepList = stepList
		
		expectedFields = ['nSteps', 'fracOn', 'avgDurOn', 'stdDurOn', 'minDurOn', 
				  'maxDurOn', 'avgDurOff', 'stdDurOff', 'minDurOff', 'maxDurOff',
				  'fracStepsOn', 'fracTimeOn', 'timeTotal']
				  
		for f in expectedFields:
			if f not in self.params:
				raise IOError('Expected parameter missing from file')
		
	def read_var(self, line):
		'''Helper function to set the current value of a variable based on a text file'''
		lineparts = line.strip().split('=')
		exec('self.params["' + lineparts[0] + '"] = ' + lineparts[1])
		
	def bounded_gaussian_list(self, nElem, avgDur, stdDur, minDur, maxDur):
		''' Generate a list of gaussian-distributed elements
	
		Returns a list of length nElem, each element of which is sampled
		from a Gaussian distribution with mean avgDur and standard deviation
		stdDur. Any elements below minDur or above maxDur will be replaced with 
		the min/max values respectively (rather than resampled). '''
		
		steps = [random.gauss(avgDur, stdDur) for _ in range(nElem)]
		return map(lambda x: min(max(minDur, x), maxDur), steps)

	def __set_seq(self):
		'''Generates a list of on/off steps based on the current parameters.
		
		Sets self.stepList to a list of tuples (OnOff[boolean], Duration[float]).
		The durations of on steps and off steps are Gaussian-distributed as per the 
		means and standard deviations set upon initialization, except that values sampled
		outside the [min, max] range are set to the closest endpoint.'''
	
		# Decide how many 'on' and 'off' timesteps
		nOn = round(self.params['fracOn'] * self.params['nSteps'])
		nOff = self.params['nSteps'] - nOn
	
		# Make lists of 'on' and 'off' timesteps separately, using individual params
		# Each step is represented as a tuple: (Boolean, double) where the first 
		# element can be True (on) or False (off) and the second gives the duration.
		onList	= self.bounded_gaussian_list(int(nOn),	self.params['avgDurOn'],	 self.params['stdDurOn'],  
											  self.params['minDurOn'],	self.params['maxDurOn'])
		onList = map(lambda val: (True, val), onList)
	
		offList = self.bounded_gaussian_list(int(nOff), self.params['avgDurOff'], self.params['stdDurOff'], 
											  self.params['minDurOff'], self.params['maxDurOff'])
		offList = map(lambda val: (False, val), offList)
	
		# Combine and shuffle on and off lists
		steps = onList + offList
		random.shuffle(steps)
		self.stepList = steps
		(self.params['fracStepsOn'], self.params['fracTimeOn'], self.params['timeTotal']) = self.__distribution_details()

	def save_distribution(self, filepath=""):
		'''Saves the current parameters and list of steps in a text file
		
		Header section includes all current parameters (those given to __init__) and
		summary statistics (actual fraction of steps on, actual fraction of time on, and
		total time) in the format varName=value (one value per line).  Body contains 
		the list of steps (one step per line) in the format OnOff[boolean],Duration[float]'''
		
		if filepath == "":
			timestamp = datetime.datetime.fromtimestamp(time.time()).strftime('%Y%m%d%H%M%S')
		
			filename = timestamp + '_fracOn' + str(int(round(100*self.params['fracOn']))) + \
					   '_fracTimeOn' + str(int(round(100*self.params['fracTimeOn']))) + \
					   '_timeTotal' + str(int(round(self.params['timeTotal']))) + '_' + \
					   str(self.nInstances) + '.txt'
			try:
				os.makedirs(self.datapath)
			except:
				pass
			filepath = os.path.join(self.datapath, filename)		

		f = open(filepath, 'w+')
		
		f.write('Summary statistics\r\n')
		for var in ['fracStepsOn', 'fracTimeOn', 'timeTotal']:
			self.write_var(f, var)
			
		f.write('Parameters used in generation\r\n')
		for var in ['nSteps', 'fracOn', 'avgDurOn', 'stdDurOn', 'minDurOn', 'maxDurOn', 
										'avgDurOff','stdDurOff','minDurOff','maxDurOff']:
			self.write_var(f,var)

		f.write(self.listStartMarker)
		for step in self.stepList:
			f.write(str(step[0])+ ',' + str(step[1]) + '\r\n')

		f.close()
		
		return filepath

		
	def write_var(self, f, varString):
		'''Helper function to write a variable to a text file'''
		f.write(varString + '=' + str(eval('self.params["' + varString + '"]')) + '\r\n')
		


	def __distribution_details(self):
		''' Returns summary statistics for a list of timesteps.
	
		Expects a list stepList of tuples (isStepOn, stepDuration) with 
		boolean first element and double second element.  Returns a 3-tuple
		with summary statistics: (fracOn, timeOn, timeTotal)
	
		fracStepsOn: what fraction of the steps have first element True
		fracTimeOn: total stepDuration for steps that are on / total stepDuration
		timeTotal: total stepDuration of all steps'''
	
		fracStepsOn = (sum([step[0] for step in self.stepList]) + 0.0)/len(self.stepList)
		timeTotal = sum([step[1] for step in self.stepList])
		fracTimeOn = sum([step[1] if step[0] else 0 for step in self.stepList])/timeTotal

	
		return (fracStepsOn, fracTimeOn, timeTotal)
		
	
	

	

class MicToggler():
	'''Class to handle turning microphone levels up/down according to a sequence of steps'''
	path = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
	appPath = os.path.join(path, 'nircmd', 'nircmd')

	def __init__(self, sequence, level=100, micName="Microphone"):
		'''Creates a MicToggler object to server a sequence of steps.  sequence should be
		a list of tuples of the form (onoff, duration) where onoff is a Boolean determining
		whether the microphone goes to full volume (True) or silent (False) this step and 
		duration is the length of the step in seconds.  level is the microphone level that should
		be set during 'full volume' periods as a percentage of true full volume (0-100).  
		micName is the name of the microphone that should be turned up/down.'''
		self.sequence = sequence
		self.micName = micName
		self.setLevel(level)
		self.currentlyToggling = False
		self.setMicAsDefault(micName)

	def stop(self):
		'''Stop toggling and return microphone volume to full.  Only call after start since
		otherwise self.t will not be defined'''
		self.t.cancel()
		self.currentlyToggling = False
		self.makeMicLoud() # set to full volume at conclusion.
		
	def setMicVol(self, volBool):
		'''Set microphone volume to full  (if volBool) or silent (else)'''
		if volBool:
			self.makeMicLoud()
		else:
			self.makeMicSilent()
	
	def makeMicLoud(self):
		'''Turn microphone volume to full (defined by self.level)'''
		print 'make loud'
		if os.name == 'posix':
			return
		sp.call([self.appPath, 'setsysvolume', self.level, self.micName])
	
	def makeMicSilent(self):
		'''Turn microphone volume to 0; do not mute'''
		print 'make silent'
		if os.name == 'posix':
			return
		sp.call([self.appPath, 'setsysvolume', '0', self.micName])
		
	def __doStep(self):
		self.t.cancel()
		self.setMicVol(self.sequence[self.iStep][0])
		if self.iStep < len(self.sequence) and self.currentlyToggling:
			self.iStep += 1
			self.t = threading.Timer(self.sequence[self.iStep][1], self.__doStep)
			self.t.start()
		else:
			self.stop()
	
	def run(self):
		'''Start toggling the microphone volume according to the sequence'''
		self.currentlyToggling = True
		self.iStep = 0
		self.t = threading.Timer(0.01, self.__doStep)
		self.t.start()
		
	@staticmethod
	def showMicList():
		'''Display a list of available microphones'''
		if os.name == 'posix':
			print 'show mic list'
			return
		sp.call([MicToggler.appPath, 'showsounddevices'])
		
	def setMicAsDefault(self, micName=""):
		'''Set this microphone to be the default which will be turned up/down'''
		if len(micName) > 0:
			self.micName = micName
		if os.name == 'posix':
			print 'set default mic'
			return
		sp.call([self.appPath, 'setdefaultsounddevice', self.micName, '1']) # default multimedia device
		sp.call([self.appPath, 'setdefaultsounddevice', self.micName, '2']) # default communications device

	def setLevel(self, percLevel):
		'''Set level (0-100) to use as 'full volume' level fo rhte microphone'''
		self.level = str(int(65536.*percLevel/100.))

def test_step_distribution():

	'''Basic testing of command-line interface for StepDistribution and MicToggler'''
	nSteps = 66
	fracOn = 0.5
	avgDurOn = 3
	stdDurOn = .5
	minDurOn = 2
	maxDurOn = 4
	
	avgDurOff = 2
	stdDurOff = 1
	minDurOff = 0
	maxDurOff = 4
	
	steps = StepDistribution({'nSteps': nSteps, 
							  'fracOn': fracOn, 
							  'avgDurOn': avgDurOn,	 
							  'stdDurOn': stdDurOn, 
							  'minDurOn': minDurOn,	 
							  'maxDurOn': maxDurOn, 
							  'avgDurOff': avgDurOff, 
							  'stdDurOff': stdDurOff, 
							  'minDurOff': minDurOff, 
							  'maxDurOff': maxDurOff})
	print (steps.params['fracStepsOn'], steps.params['timeTotal'], steps.params['fracTimeOn']) 
	filename = steps.save_distribution()
	
	steps2 = StepDistribution({'nSteps': nSteps, 
							  'fracOn': 0.2, 
							  'avgDurOn': avgDurOn,	 
							  'stdDurOn': stdDurOn, 
							  'minDurOn': minDurOn,	 
							  'maxDurOn': maxDurOn, 
							  'avgDurOff': avgDurOff, 
							  'stdDurOff': stdDurOff, 
							  'minDurOff': minDurOff, 
							  'maxDurOff': maxDurOff})
	steps2.save_distribution()
	
	newsteps = StepDistribution(filename)
	newsteps.save_distribution()
	
	mt = MicToggler(steps.stepList)
	mt.showMicList()
	mt.setMicAsDefault()
	t = threading.Timer(10.0, mt.stop)
	t.start()
	mt.start()
	
class TogglerGui(wx.Frame):
  
	def __init__(self):
		'''Create the TogglerGui object.  After initialization it will have the following 
		input objects available:
		
		self.load, self.save, self.quit (menu items)
		self.explanation (hover text)
				
		self.numStepsBox
		self.fracOnBox
		self.durOnBox, self.durOffBox
		self.varOnBox, self.varOffBox
		self.minOnBox, self.maxOnBox, self.minOffBox, self.maxOffBox
		
		self.statPercOn
		self.statTimeOn
		self.statDur
		
		self.micChoice
		self.showMicButton
		self.micLevelSlider
		
		self.startButton
		self.stopButton
		
		To change default, min, max values, see InitUI.
		'''
		
		super(TogglerGui, self).__init__(None, style=wx.MAXIMIZE_BOX | wx.RESIZE_BORDER 
			| wx.SYSTEM_MENU | wx.CAPTION |	 wx.CLOSE_BOX | wx.MINIMIZE_BOX, 
			title='MicToggler', 
			size=(850, 700)) # this is the default size (w x h) of the app in pixels
		self.theDistribution = []
		self.Centre()
		self.InitUI()
		self.Show()
		
		# Make the default size for all objects 14 pt
		font = wx.SystemSettings_GetFont(wx.SYS_SYSTEM_FONT)
		font.SetPointSize(14)
		self.SetFont(font)
		
	def InitUI(self):
		'''Set up the menu bar and lay out buttons and text input'''
	
		self.borderSize = 10; # Padding around elements
		
		# Create a menu bar and a single 'file' menu with load, save, & quit items
		menubar = wx.MenuBar()
		fileMenu = wx.Menu()
		
		# Add menu items
		self.load = fileMenu.Append(wx.ID_ANY, '&Load sequence...')
		self.save = fileMenu.Append(wx.ID_SAVE, '&Save sequence as...')
		self.quit = fileMenu.Append(wx.ID_EXIT, '&Quit')
		
		# Make the menu items call their associated functions when selected
		self.Bind(wx.EVT_MENU, self.onLoad, self.load)
		self.Bind(wx.EVT_MENU, self.onSave, self.save)
		self.Bind(wx.EVT_MENU, self.onQuit, self.quit)
		
		# Disable save upon opening application, until data is there to save
		self.save.Enable(False)
		
		# Finally create and attach the menubar
		menubar.Append(fileMenu, '&File')
		self.SetMenuBar(menubar)
		
		# Now create the layout (parameter entry/viewing, create, start/pause buttons)
		# Distribution parameters:
		#	Number of steps
		#	Average frac 'on'	  | 
		#	Average duration 'on' | Average duration 'off'
		#	Variability 'on'	  | Variability 'off'
		#	Minimum/maximum 'on'  | Minimum/maximum 'off'
		#
		# --
		# Generate (new)  |		Stats:
		#						Fraction steps on
		#						Fraction time on
		#						Total duration
		# 
		# --
		#
		# Microphone (drop-down):						Start
		# Level:										Stop

		self.panel = wx.Panel(self)
		vbox  = wx.BoxSizer(wx.VERTICAL)

		# The first segment: distribution parameters
		vboxDist = wx.BoxSizer(wx.VERTICAL) # Contains label and all parameters

		labelDist = wx.StaticText(self.panel, label='Sequence parameters:')
		
		topBox = wx.BoxSizer(wx.HORIZONTAL)
		topBox.Add(labelDist, proportion=1, flag=wx.LEFT|wx.EXPAND, border=self.borderSize)
		topBox.Add((100,-1))
		topBox.AddStretchSpacer()
		self.explanation = wx.StaticText(self.panel, label='')
		self.explanation.SetForegroundColour(wx.RED)
		topBox.Add(self.explanation, flag=wx.RIGHT|wx.ALIGN_RIGHT|wx.EXPAND, border=self.borderSize)
		
		vboxDist.Add(topBox, flag=wx.TOP, border=self.borderSize)
		vboxDist.Add((-1, 10))
		
		# Create all numerical input boxes and set default values
		
		self.numStepsBox = self.addParamRow(vboxDist, ['Number of steps:', ''])[0]
		self.numStepsBox.SetParameters(min=1, fractionWidth=0)
		self.numStepsBox.SetValue(500)
		self.fracOnBox = self.addParamRow(vboxDist, ['Percent steps ON:', ''])[0]
		self.fracOnBox.SetParameters(min=0, max=100, fractionWidth=1)
		self.fracOnBox.SetValue(50)
		(self.durOnBox, self.durOffBox) = \
			self.addParamRow(vboxDist, ['Avg duration ON (s):', 'Avg duration OFF (s):'])
		self.durOnBox.SetParameters(min=0.01)
		self.durOnBox.SetValue(5)
		self.durOffBox.SetParameters(min=0.01)
		self.durOffBox.SetValue(5)
		(self.varOnBox, self.varOffBox) = \
			self.addParamRow(vboxDist, ['Variability ON:', 'Variability OFF:'])
		(self.minOnBox, self.maxOnBox, self.minOffBox, self.maxOffBox)	 = \
			self.addParamRow(vboxDist, ['Min/Max ON:', 'Min/Max OFF:'], type='jointtext')
		self.maxOnBox.SetParameters(min=0.01);
		self.maxOffBox.SetParameters(min=0.01);
		self.maxOnBox.SetValue(10)
		self.maxOffBox.SetValue(10)
		
			
		divider = wx.StaticLine(self.panel, wx.ID_ANY, size=wx.Size(300,3), style=wx.LI_VERTICAL)

		vbox.Add(vboxDist, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, border=self.borderSize)
		vbox.Add(divider, proportion=0, flag=wx.ALIGN_CENTER|wx.ALL, border=self.borderSize)
		
		# Plan the next horizontal layer: generate | stats.
		generateAndStatsBox = wx.BoxSizer(wx.HORIZONTAL)
		generateBox = wx.BoxSizer(wx.VERTICAL)
		statsBox = wx.BoxSizer(wx.VERTICAL)
		
		# Just the generate button on the left
		self.generate = wx.Button(self.panel, label='Generate new \nsequence', size=(100,100))
		self.flagUnsaved(False)
		generateBox.Add(self.generate, proportion=0, flag=wx.ALIGN_CENTER_HORIZONTAL|wx.ALL)		
		
		# On the right, our general statistics panel about the particular distribution
		statsPanel = wx.Panel(self.panel, size=(200,-1))
		statsPanel.SetBackgroundColour("gray")

		statsBoxInner = wx.BoxSizer(wx.VERTICAL)
		self.statPercOn = wx.StaticText(statsPanel, label='Percent steps ON: ')
		self.statTimeOn = wx.StaticText(statsPanel, label='Percent time ON: ')
		self.statDur	= wx.StaticText(statsPanel, label='Total duration (s): ')
		statsBoxInner.Add(self.statPercOn, flag=wx.ALL, border=self.borderSize)
		statsBoxInner.Add(self.statTimeOn, flag=wx.ALL, border=self.borderSize)
		statsBoxInner.Add(self.statDur, flag=wx.ALL, border=self.borderSize)
		
		statsPanel.SetSizer(statsBoxInner)
		statsBox.Add(statsPanel)
		
		# Put together and attach the generate | stats layer
		generateAndStatsBox.Add(generateBox, proportion=1, flag=wx.ALIGN_LEFT|wx.ALL|wx.EXPAND)
		generateAndStatsBox.Add(statsBox,	 proportion=1, flag=wx.ALIGN_LEFT|wx.ALL|wx.EXPAND)
		vbox.Add(generateAndStatsBox, proportion=1, flag=wx.EXPAND|wx.ALL)
		
		vbox.Add((-1, 25))
		
		divider = wx.StaticLine(self.panel, wx.ID_ANY, size=wx.Size(300,3), style=wx.LI_VERTICAL)
		vbox.Add(divider, proportion=0, flag=wx.ALIGN_CENTER_HORIZONTAL|wx.ALL)
		
		# Finally, the microphone and start/stop controls
		

		micChoiceBox = wx.BoxSizer(wx.HORIZONTAL)
		micChoiceBox.Add(wx.StaticText(self.panel, label="Microphone: "), flag=wx.ALL, border=self.borderSize)
		self.micChoice = wx.TextCtrl(self.panel, value="Microphone")
		micChoiceBox.Add(self.micChoice, flag=wx.ALL, border=self.borderSize)
		self.showMicButton = wx.Button(self.panel, label='Show all')
		micChoiceBox.Add(self.showMicButton, flag=wx.ALL, border=self.borderSize)
		
		micLevelBox = wx.BoxSizer(wx.HORIZONTAL)
		micLevelBox.Add(wx.StaticText(self.panel, label="Level when on: "), flag=wx.ALL, border=self.borderSize)
		self.micLevelSlider = wx.Slider(self.panel, value=90, minValue=0, maxValue=100,
			style=wx.SL_LABELS)
		micLevelBox.Add(self.micLevelSlider)
		
		micControlsBox = wx.BoxSizer(wx.VERTICAL)
		micControlsBox.Add(micChoiceBox)
		micControlsBox.Add(micLevelBox)
		
		
		self.startButton = wx.Button(self.panel, label='Start')
		self.startButton.Enable(False)
		self.stopButton	 = wx.Button(self.panel, label='Stop')
		self.stopButton.Enable(False)
		startButtonBox = wx.BoxSizer(wx.VERTICAL)
		startButtonBox.Add(self.startButton)
		startButtonBox.Add(self.stopButton, flag=wx.TOP, border=self.borderSize)
		
		micAndStartBox = wx.BoxSizer(wx.HORIZONTAL)
		micAndStartBox.Add(micControlsBox, proportion=.3, flag=wx.ALIGN_LEFT)
		micAndStartBox.AddStretchSpacer()
		micAndStartBox.Add(startButtonBox, proportion=.6, flag=wx.ALIGN_RIGHT)

		vbox.Add(micAndStartBox, flag=wx.EXPAND|wx.ALL, border=2*self.borderSize)
		self.panel.SetSizer(vbox)
		
		# Finally, bind events
		
		# Whenever a number input is updated, check on whether the input is still valid
		self.Bind(wx.lib.masked.EVT_NUM, self.verifyParameters)
		self.generate.Bind(wx.EVT_BUTTON, self.onGenerate)
		
		# Start and stop buttons
		self.startButton.Bind(wx.EVT_BUTTON, self.onStart)
		self.stopButton.Bind(wx.EVT_BUTTON, self.onStop)
		
		# Show mic button
		self.showMicButton.Bind(wx.EVT_BUTTON, self.onShowMic)
		
		# Bindings for mouseover explanations
		self.varOnBox.Bind(wx.EVT_ENTER_WINDOW, self.onMouseOverVar)
		self.varOnBox.Bind(wx.EVT_LEAVE_WINDOW, self.onMouseLeave)
		self.varOffBox.Bind(wx.EVT_ENTER_WINDOW, self.onMouseOverVar)
		self.varOffBox.Bind(wx.EVT_LEAVE_WINDOW, self.onMouseLeave)
		
		self.minOnBox.Bind(wx.EVT_ENTER_WINDOW, self.onMouseOverMinMax)
		self.minOnBox.Bind(wx.EVT_LEAVE_WINDOW, self.onMouseLeave)
		self.minOffBox.Bind(wx.EVT_ENTER_WINDOW, self.onMouseOverMinMax)
		self.minOffBox.Bind(wx.EVT_LEAVE_WINDOW, self.onMouseLeave)
		self.maxOnBox.Bind(wx.EVT_ENTER_WINDOW, self.onMouseOverMinMax)
		self.maxOnBox.Bind(wx.EVT_LEAVE_WINDOW, self.onMouseLeave)
		self.maxOffBox.Bind(wx.EVT_ENTER_WINDOW, self.onMouseOverMinMax)
		self.maxOffBox.Bind(wx.EVT_LEAVE_WINDOW, self.onMouseLeave)
		
		
	def addParamRow(self, parentBox, labels, type='text'):
		'''Helper function to add two labeled numerical input boxes in a row.
		labels should have two elements, both strings to name the input
		returns an 2ple of textcontrol inputs corresponding to those inputs'''
		
		textControls = []
		
		# Parameters will be in two columns, 'on' on one side and 'off' on the other
		fracBox = wx.BoxSizer(wx.HORIZONTAL)
		fracOnBox = wx.BoxSizer(wx.HORIZONTAL)
		fracOffBox = wx.BoxSizer(wx.HORIZONTAL)
		
		labelOn = wx.StaticText(self.panel, label=labels[0], size=(120,20))
		fracOnBox.Add(labelOn, border=2)
		fracOnBox.Add((15, -1))
		textControls.append(wx.lib.masked.NumCtrl(self.panel, allowNone=False, \
			groupDigits=False, limitOnFieldChange=True, selectOnEntry=True, min=0, \
			fractionWidth=2))
		fracOnBox.Add(textControls[0], proportion=0)
		if type=="jointtext":
			textControls.append(wx.lib.masked.NumCtrl(self.panel, allowNone=False, \
				groupDigits=False, limitOnFieldChange=True, selectOnEntry=True, min=0, \
				fractionWidth=2))
			fracOnBox.Add((15,-1))
			fracOnBox.Add(textControls[1], proportion=0)
		
		
		labelOff = wx.StaticText(self.panel, label=labels[1], size=(120, 20))
		fracOffBox.Add(labelOff, border=2)
		if len(labels[1])>0:
			fracOffBox.Add((15, -1))
			textControls.append(wx.lib.masked.NumCtrl(self.panel, allowNone=False, \
				groupDigits=False, limitOnFieldChange=True, selectOnEntry=True, min=0, \
				fractionWidth=2))
			fracOffBox.Add(textControls[-1], proportion=0)
			if type=="jointtext":
				textControls.append(wx.lib.masked.NumCtrl(self.panel, allowNone=False, \
					groupDigits=False, limitOnFieldChange=True, selectOnEntry=True, min=0, \
					fractionWidth=2))
				fracOffBox.Add((15,-1))
				fracOffBox.Add(textControls[-1], proportion=0)
		
		fracBox.Add(fracOnBox, proportion=1, flag=wx.ALL|wx.EXPAND, border=2)
		fracBox.Add((20,-1))
		fracBox.Add(fracOffBox, proportion=1, flag=wx.ALL|wx.EXPAND, border=2)
		parentBox.Add(fracBox, proportion=1, flag=wx.ALL|wx.EXPAND, border=8)
		
		return textControls 
		
	def verifyParameters(self, event):
		'''Called every time any numerical input is updated.  Verify that min time ON 
		< max time ON, min time OFF < max time OFF.'''
		epsilon = 0.01;
		self.minOnBox.SetMax(self.maxOnBox.GetValue() - epsilon)
		self.maxOnBox.SetMin(self.minOnBox.GetValue() + epsilon)
		self.minOffBox.SetMax(self.maxOffBox.GetValue() - epsilon)
		self.maxOffBox.SetMin(self.minOffBox.GetValue() + epsilon)	
		
		
	def getDistParams(self):
		'''Accesses current field values to return a dictionary that can be passed to 
		the StepDistribution constructor:
		nSteps: number of (on/off) steps to create
		fracOn: what fraction of the STEPS should be on
		avgDurOn: mean (s) for the Gaussian distribution used to generate ON steps
		stdDurOn: standard deviation (s) for the Gaussian distribution used for ON steps
		minDurOn: minimum duration (s) of ON steps
		maxDurOn: maximum duration (s) of ON steps
		avgDurOff: mean (s) for the Gaussian distribution used to generate OFF steps
		stdDurOff: standard deviation (s) for the Gaussian distribution used for OFF steps
		minDurOff: minimum duration (s) of OFF steps
		maxDurOff: maximum duration (s) of OFF steps'''
		
		params = {};
		params['nSteps']	= self.numStepsBox.GetValue()
		params['fracOn']	= self.fracOnBox.GetValue()/100 # Input is in percent
		
		params['avgDurOn']	= self.durOnBox.GetValue()
		params['avgDurOff'] = self.durOffBox.GetValue()
		
		params['stdDurOn']	= self.varOnBox.GetValue() * params['avgDurOn'] / 100 # Input in percent avg
		params['stdDurOff'] = self.varOffBox.GetValue() * params['avgDurOff'] / 100
		
		params['minDurOn']	= self.minOnBox.GetValue()
		params['minDurOff'] = self.minOffBox.GetValue()
		params['maxDurOn']	= self.maxOnBox.GetValue()
		params['maxDurOff'] = self.maxOffBox.GetValue()

		return params
		
	def setInput(self, params):
		'''Inverse of getDistParams--start with param dict and set values (for loading a file)'''
		self.numStepsBox.SetValue(params['nSteps'])
		self.fracOnBox.SetValue(params['fracOn']*100) # Input is in percent
		
		self.durOnBox.SetValue(params['avgDurOn'])
		self.durOffBox.SetValue(params['avgDurOff'])
		
		self.varOnBox.SetValue(params['stdDurOn'] / params['avgDurOn'] * 100) # Input in percent avg
		self.varOffBox.SetValue(params['stdDurOff'] / params['avgDurOff'] * 100) # Input in percent avg
		
		self.minOnBox.SetValue(params['minDurOn'])
		self.minOffBox.SetValue(params['minDurOff'])
		self.maxOnBox.SetValue(params['maxDurOn'])
		self.maxOffBox.SetValue(params['maxDurOff'])
		
	def flagUnsaved(self, toggle):
		self.isUnsaved = toggle;
		if toggle:
			self.SetTitle('MicToggler - UNSAVED SEQUENCE')
			#self.status.SetLabel('Unsaved sequence')
			#self.status.SetBackgroundColour("yellow")
		#else:
			#self.status.SetLabel('')
			#self.status.SetBackgroundColour(self.panel.GetBackgroundColour())
			
	def setStats(self, params):
		self.statPercOn.SetLabel('Percent steps ON: %3.1f' % (params['fracStepsOn']*100))
		self.statTimeOn.SetLabel('Percent time ON: %3.1f' % (params['fracTimeOn']*100))
		
		# Display the time in hours:minutes:seconds
		t = params['timeTotal']
		(hours, rem) = divmod(t,3600)
		(minutes, seconds) = divmod(rem, 60)
		self.statDur.SetLabel('Total duration (s): %i:%i:%i' % (hours, minutes, seconds))
		
	def onLoad(self, event):
		'''Function called when the "load distribution" menu item is selected'''
		
		if self.isUnsaved:
		
			if wx.MessageBox("Current sequence has not been saved! Proceed?", "Please confirm", wx.ICON_QUESTION | wx.YES_NO, self) == wx.NO:
				return

		openFileDialog = wx.FileDialog(self, "Open distribution file", "", "",
			 "MicToggler files (*.txt)|*.txt", wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)

		if openFileDialog.ShowModal() == wx.ID_CANCEL:
			return
		
		try:
			filepath = str(openFileDialog.GetPath())
			self.theDistribution = StepDistribution(filepath)
			self.setStats(self.theDistribution.params)
			self.setInput(self.theDistribution.params)
		except:
			wx.MessageBox("Sequence could not be loaded from this file: " + str(sys.exc_info()[0]) + str(sys.exc_info()[1]))
		
		self.flagUnsaved(False)
		
		self.save.Enable(False)
		self.startButton.Enable(True)
		
		self.SetTitle('MicToggler - ' + os.path.basename(filepath))
		
	def onSave(self, event):
		'''Function called when the "save distribution" menu item is selected'''
		
		saveFileDialog = wx.FileDialog(self, "Save distribution file", "", "",
			"MicToggler files (*.txt)|*.txt", wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)

		if saveFileDialog.ShowModal() == wx.ID_CANCEL:
			return 
			
		try:
			filepath = str(saveFileDialog.GetPath())
			self.theDistribution.save_distribution(filepath)
			self.flagUnsaved(False)
			self.SetTitle('MicToggler - ' + os.path.basename(filepath))
		except:
			wx.MessageBox("Sequence could not be saved: " + str(sys.exc_info()[0]) + str(sys.exc_info()[1]))

	def onQuit(self, event):
		'''Function called when the "quit" menu item is selected'''
		if self.isUnsaved:
			if wx.MessageBox("Current sequence has not been saved! Quit anyway?", "", wx.ICON_QUESTION | wx.YES_NO, self) == wx.NO:
				return
		self.Close()		
		
	def onGenerate(self, event):
		'''Function called when the 'generate' button is pressed'''
		self.generate.Enable(False) # Disable this button until generation is complete
		
		# Create the StepDistribution based on the sequence parameters
		self.theDistribution = StepDistribution(self.getDistParams())
		
		# Display statistics about the particular sequence generated
		self.setStats(self.theDistribution.params) 
		
		self.flagUnsaved(True)
		
		self.save.Enable(True) # Allow saving now that we have a sequence
		self.startButton.Enable(True) # Allow starting toggling
		self.generate.Enable(True) # Re-enable this button after generation is complete
		
	def onStart(self, event):
		# Create mictoggler and start
		self.theToggler = MicToggler(self.theDistribution.stepList, level=self.micLevelSlider.GetValue(), 
			micName=self.micChoice.GetValue())
		
		self.startButton.Enable(False)
		self.stopButton.Enable(True)
		self.theToggler.run()
	
	def onStop(self, event):
		self.theToggler.stop()
		self.startButton.Enable(True)
		self.stopButton.Enable(False)
	
	def onShowMic(self, event):
		MicToggler.showMicList()
		
	def onMouseOverVar(self, event):
		self.explanation.SetLabel('Standard deviation of step length, as percentage of the average duration')
		
	def onMouseOverMinMax(self, event):
		self.explanation.SetLabel('Values generated that are outside this range will be cast to the min/max value')
	
	def onMouseLeave(self, event):
		self.explanation.SetLabel('')
	
def make_gui():
	app = wx.App()
	TogglerGui()
	app.MainLoop()

make_gui()