# for localized messages
from . import _

import os, re

from enigma import eServiceReference, eDVBDB

from Components.ActionMap import ActionMap
from Components.config import config
from Components.Label import Label
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

from twisted.internet import reactor
from twisted.internet.protocol import ClientCreator
from twisted.protocols.ftp import FTPClient

from FTPDownloader import FTPDownloader

DIR_ENIGMA2 = '/etc/enigma2/'
DIR_TMP = '/tmp/'

class ChannelsImporter(Screen):
	skin = """
	<screen position="0,0" size="1280,35" backgroundColor="transpBlack" flags="wfNoBorder" >
		<widget name="action" position="5,3" size="435,25" font="Regular;22" backgroundColor="transpBlack" borderWidth="3" borderColor="black"/>
		<widget name="status" position="465,5" size="435,25" font="Regular;22" halign="center" backgroundColor="transpBlack" borderWidth="2" borderColor="black"/>
	</screen>"""

	def __init__(self, session):
		print "[ChannelsImporter][__init__] Starting..."
		self.session = session
		Screen.__init__(self, session)
		Screen.setTitle(self, _("Channels importer"))

		self["action"] = Label(_("Starting importer"))
		self["status"] = Label("")

		self["actions"] = ActionMap(["SetupActions"],
		{
			"cancel": self.keyCancel,
		}, -2)
		self.onFirstExecBegin.append(self.firstExec)

	def firstExec(self):
		self.checkConnection()

	def checkConnection(self):
		print "[ChannelsImporter] Checking FTP connection to remote receiver"
		self["action"].setText(_('Starting importer...'))
		self["status"].setText(_("Checking FTP connection to remote receiver"))
		timeout = 5
		self.currentLength = 0
		self.total = 0
		self.working = True
		creator = ClientCreator(reactor, FTPClient, config.plugins.ChannelsImporter.username.value, config.plugins.ChannelsImporter.password.value, config.plugins.ChannelsImporter.passive.value)
		creator.connectTCP(self.getRemoteAddress(), config.plugins.ChannelsImporter.port.value, timeout).addCallback(self.checkConnectionCallback).addErrback(self.checkConnectionErrback)

	def checkConnectionErrback(self, *args):
		print "[ChannelsImporter] Could not connect to the remote IP"
		print "[ChannelsImporter] Error messages:", args
		self.showError(_('Could not connect to the remote IP'))

	def checkConnectionCallback(self, ftpclient):
		print "[ChannelsImporter] Connection to remote IP ok"
		self["action"].setText(_('Connection to remote IP ok'))
		self["status"].setText(_(""))
		ftpclient.quit()
		self.fetchRemoteBouquets()

	def fetchRemoteBouquets(self):
		print "[ChannelsImporter] Downloading bouquets.tv and bouquets.radio"
		self.readIndex = 0
		self.workList = []
		self.workList.append('bouquets.tv')
		self.workList.append('bouquets.radio')
		self["action"].setText(_('Downloading channel indexes...'))
		self["status"].setText(_("%d/%d") % (self.readIndex + 1, len(self.workList)))
		self.download(self.workList[0]).addCallback(self.fetchRemoteBouquetsCallback).addErrback(self.fetchRemoteBouquetsErrback)

	def fetchRemoteBouquetsErrback(self, msg):
		print "[ChannelsImporter] Download from remote failed. %s" % msg
		self.showError(_('Download from remote failed %s') % msg)

	def fetchRemoteBouquetsCallback(self, msg):
		self.readIndex += 1
		if self.readIndex < len(self.workList):
			self["status"].setText(_("%d/%d") % (self.readIndex + 1, len(self.workList)))
			self.download(self.workList[self.readIndex]).addCallback(self.fetchRemoteBouquetsCallback).addErrback(self.fetchRemoteBouquetsErrback)
		else:
			self.readBouquets()

	def getBouquetsList(self, bouquetFilenameList, bouquetfile):
		file = open(bouquetfile)
		lines = file.readlines()
		file.close()
		if len(lines) > 0:
			for line in lines:
				result = re.match("^.*FROM BOUQUET \"(.+)\" ORDER BY.*$", line) or re.match("[#]SERVICE[:] (?:[0-9a-f]+[:])+([^:]+[.](?:tv|radio))$", line, re.IGNORECASE)
				if result is None:
					continue
				bouquetFilenameList.append(result.group(1))

	def readBouquets(self):
		bouquetFilenameList = []
		self.getBouquetsList(bouquetFilenameList, DIR_TMP + 'bouquets.tv')
		self.getBouquetsList(bouquetFilenameList, DIR_TMP + 'bouquets.radio')
		self.readIndex = 0
		self.workList = []
		for listindex in range(len(bouquetFilenameList)):
			self.workList.append(bouquetFilenameList[listindex])
		self.workList.append('lamedb')
		self["action"].setText(_('Downloading bouquets...'))
		self["status"].setText(_("%d/%d") % (self.readIndex + 1, len(self.workList)))
		self.download(self.workList[0]).addCallback(self.readBouquetsCallback).addErrback(self.readBouquetsErrback)

	def readBouquetsErrback(self, msg):
		print "[ChannelsImporter] Download from remote failed. %s" % msg
		self.showError(_('Download from remote failed %s') % msg)

	def readBouquetsCallback(self, msg):
		self.readIndex += 1
		if self.readIndex < len(self.workList):
			self["status"].setText(_("%d/%d") % (self.readIndex + 1, len(self.workList)))
			self.download(self.workList[self.readIndex]).addCallback(self.readBouquetsCallback).addErrback(self.readBouquetsErrback)
		elif len(self.workList) > 0:
			# Download alternatives files where services have alternatives
			self["action"].setText(_('Checking for alternatives...'))
			self["status"].setText("")
			self.findAlternatives()
			self.alternativesCounter = 0
			if len(self.alternatives) > 0:
				self["action"].setText(_('Downloading alternatives...'))
				self["status"].setText(_("%d/%d") % (self.alternativesCounter + 1, len(self.alternatives)))
				self.download(self.alternatives[self.alternativesCounter]).addCallback(self.downloadAlternativesCallback).addErrback(self.downloadAlternativesErrback)
			self.processFiles()
		else:
			print "[ChannelsImporter] There were no remote bouquets to download"
			self.showError(_('Download from remote failed %s'))

	def downloadAlternativesErrback(self, msg):
		print "[ChannelsImporter] Download from remote failed. %s" % msg
		self.showError(_('Download from remote failed %s') % msg)

	def downloadAlternativesCallback(self, string):
		self.alternativesCounter += 1
		if self.alternativesCounter < len(self.alternatives):
			self["status"].setText(_("%d/%d") % (self.alternativesCounter + 1, len(self.alternatives)))
			self.download(self.alternatives[self.alternativesCounter]).addCallback(self.downloadAlternativesCallback).addErrback(self.downloadAlternativesErrback)

	def processFiles(self):
		allFiles = self.workList + self.alternatives + ["bouquets.tv", "bouquets.radio"]
		self["action"].setText(_('Removing current channel list...'))
		self["status"].setText("")
		for target in ["lamedb", "bouquets.", "userbouquet."]:
			self.removeFiles(DIR_ENIGMA2, target)
		self["action"].setText(_('Loading new channel list...'))
		for filename in allFiles:
			self.copyFile(DIR_TMP + filename, DIR_ENIGMA2 + filename)
			self.removeFiles(DIR_TMP, filename)
		db = eDVBDB.getInstance()
		db.reloadServicelist()
		db.reloadBouquets()
		self.close(True)

	def findAlternatives(self):
		print "[ChannelsImporter] Checking for alternatives"
		self.alternatives = []
		for filename in self.workList:
			if filename != "lamedb":
				try:
					fp = open(DIR_TMP + filename)
					lines = fp.readlines()
					fp.close()
					for line in lines:
						if '#SERVICE' in line and int(line.split()[1].split(":")[1]) & eServiceReference.mustDescent:
							result = re.match("^.*FROM BOUQUET \"(.+)\" ORDER BY.*$", line) or re.match("[#]SERVICE[:] (?:[0-9a-f]+[:])+([^:]+[.](?:tv|radio))$", line, re.IGNORECASE)
							if result is None:
								continue
							self.alternatives.append(result.group(1))
				except:
					pass

	def showError(self, message):
		mbox = self.session.open(MessageBox, message, MessageBox.TYPE_ERROR)
		mbox.setTitle(_("Channels importer"))
		self.close()

	def keyCancel(self):
		self.close()

	def removeFiles(self, targetdir, target):
		targetLen = len(target)
		for root, dirs, files in os.walk(targetdir):
			for name in files:
				if target in name[:targetLen]:
					os.remove(os.path.join(root, name))

	def copyFile(self, source, dest):
		import shutil
		shutil.copy2(source, dest)

	def getRemoteAddress(self):
		return '%d.%d.%d.%d' % (config.plugins.ChannelsImporter.ip.value[0], config.plugins.ChannelsImporter.ip.value[1], config.plugins.ChannelsImporter.ip.value[2], config.plugins.ChannelsImporter.ip.value[3])

	def download(self, file, contextFactory = None, *args, **kwargs):
		print "[ChannelsImporter] Downloading remote file %s" % file
		client = FTPDownloader(
			self.getRemoteAddress(),
			config.plugins.ChannelsImporter.port.value,
			DIR_ENIGMA2 + file,
			DIR_TMP + file,
			config.plugins.ChannelsImporter.username.value,
			config.plugins.ChannelsImporter.password.value,
			*args,
			**kwargs
		)
		return client.deferred
