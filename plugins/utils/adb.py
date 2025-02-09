import subprocess
import os
import re
import time
import platform
import threading
import binascii

from utils import base

ADB_EXEC_PATH = '/usr/local/bin/adb' if platform.system() == 'Darwin' else '/usr/bin/adb'

def start_adb_server():
	exec_adb_cmd(['adb', 'start-server'])
	# wait adb server start
	time.sleep(3)
	server_status = {
		'online': False
	}
	def check_online(line):
		reg_obj = re.search(r'List of devices attached', line)
		server_status['online'] |= (reg_obj is not None)

	if exec_adb_cmd(['adb', 'devices'], logger=check_online) != 0 or not server_status['online']:
		return False
	else:
		return True

def scan_local_device():
	device = {
		'serial': None
	}
	def parse_serial(line):
		reg_obj = re.search(r'(emulator-\d+)', line)
		if reg_obj:
			device['serial'] = reg_obj.groups()[0]

	if exec_adb_cmd(['adb', 'devices'], logger=parse_serial) != 0:
		return None
	return device['serial']

def connect_to_device(serial):
	# local device is already connected
	if re.match(r'emulator-\d+', serial):
		return True
	connection = {
		'status': False
	}
	def parse_connection_status(line):
		reg_obj = re.search(r'connected to', line)
		connection['status'] |= (reg_obj is not None)

	if exec_adb_cmd(['adb', 'connect', serial], logger=parse_connection_status) != 0 or not connection['status']:
		return False
	# TODO
	# prevent adb response with 'device offline'
	time.sleep(2)
	if exec_adb_cmd(['adb', 'shell', 'echo', 'ok'], serial=serial) != 0:
		return False
	return True

"""
:param args: [str]
:param serial: str
:param logger: lambda: (str) -> {}
"""
def exec_adb_cmd(args, serial=None, logger=None):
	adb_env = os.environ.copy()
	if serial:
		adb_env['ANDROID_SERIAL'] = serial
	# TODO replace ADB_EXEC_PATH
	with subprocess.Popen(args, executable=ADB_EXEC_PATH, stdout=subprocess.PIPE, env=adb_env) as process:
		def timeout_callback():
			print('process has timeout')
			process.kill()

		# kill process in timeout seconds unless the timer is restarted
		watchdog = base.WatchdogTimer(timeout=30, callback=timeout_callback, daemon=True)
		watchdog.start()
		for line in process.stdout:
			# don't invoke the watcthdog callback if do_something() takes too long
			with watchdog.blocked:
				if not line:
					process.kill()
					break
				if logger and callable(logger):
					logger(str(line))
				os.write(1, line)
				watchdog.restart()
		watchdog.cancel()
	return process.returncode

def spawn_logcat(serial=None, logger=None):
	def read_log():
		adb_env = os.environ.copy()
		if serial:
			adb_env['ANDROID_SERIAL'] = serial

		# ignore return code
		subprocess.call(args=["adb", "logcat", "-c"], executable=ADB_EXEC_PATH, env=adb_env)

		process = subprocess.Popen([
			"adb", "logcat",
			"-v", "tag",
			"-s", "TestResult.TestExecutionRecord"
		], executable=ADB_EXEC_PATH, stdout=subprocess.PIPE, env=adb_env)
		while True:
			line = process.stdout.readline()
			if not line:
				continue
			if logger and callable(logger):
				logger(str(line, encoding='utf-8'))

	t = threading.Thread(target=read_log, daemon=True)
	t.start()


def parse_logcat(chunk_cache, log):
	idx = log.find('TestResult.TestExecutionRecord')
	if idx == -1:
		return None

	data_str = log[idx + len('TestResult.TestExecutionRecord') + 1:]
	data_str = data_str.strip()

	data_str = chunk_cache.parse_chunk_data(data_str)
	if not data_str:
		return None

	print('data_str: ' + data_str)
	try:
		return base.base64_decode(data_str)
	except binascii.Error as e:
		print('Decode base64 data error: ' + str(e))
		return None

def get_app_version(serial, app_id):
	cur_apk = {
		'version': None
	}
	def check_apk_version(line):
		# print('"%s"' % line)
		reg_obj = re.search(r'versionName=(release-\d{8}-[.0-9]+)', line)
		if reg_obj:
			cur_apk['version'] = reg_obj.groups()[0]

	exec_adb_cmd([
		'adb', 'shell', 'dumpsys', 'package', app_id
	], serial=serial, logger=check_apk_version)
	return cur_apk['version']

if __name__ == '__main__':
	version = get_app_version(serial='05849a9b', app_id='com.chi.ssetest')
	print(version)