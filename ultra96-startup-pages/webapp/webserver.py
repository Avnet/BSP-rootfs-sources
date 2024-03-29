###############################################################################
#
# Copyright (C) 2019 Xilinx, Inc.  All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
# of the Software, and to permit persons to whom the Software is furnished to do
# so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS  BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
###############################################################################
#
# Author: Michael Chyziak <chyziak@xilinx.com>
#
###############################################################################

from flask import Flask, render_template, request, redirect, url_for
from multiprocessing import Pipe
import random
import crypt
import subprocess
import os.path
import os
import glob
import sys
import time
import multiprocessing
import signal
import uuid
import re

CUR_DIRECTORY = os.path.split(os.path.abspath(__file__))[0]
ALERT = -1

app = Flask(__name__)

global timer_status, timeout, elapsed_time, pconn, cconn
timer_status = "timer_disabled"
timeout = 15
elapsed_time = 5
pconn, cconn = Pipe()

leds = {
    "ds2" : "LED0/D3",
    "ds3" : "LED1/D4",
    "ds4" : "LED2/D6",
    "ds5" : "LED3/D7"
}

triggers = [
        { "label" : "Off"       , "definition" : "Turns the led Off",              "file" : "brightness", "value" : "0"},
        { "label" : "On"        , "definition" : "Turns the led on",               "file" : "brightness", "value" : "255"},
        { "label" : "Heartbeat" , "definition" : "Blinks in a heart beat fashion", "file" : "trigger",    "value" : "heartbeat"},
        { "label" : "mmc1"      , "definition" : "Flickers with mmc1 activity",    "file" : "trigger",    "value" : "mmc1"}
]

@app.route('/')
@app.route('/home.html', methods=['GET', 'POST'])
def home():

	raw = subprocess.check_output(['ifconfig','-a'])
	line = raw.find(b'wlan')
	raw = raw[line:]
	hwline = raw.find(b"HWaddr")
	raw = raw[hwline+6:hwline+24]
	raw = raw.replace(b":",b"")
	return render_template("Home/home.html", value=raw.decode('utf-8'))

def connect_to_wifi(name,passphrase):
        name=name
        passphrase=passphrase
        ssid=""
        service_name=""
        wififound=""
        os.system("connmanctl enable wifi")
        os.system("connmanctl scan wifi")
        proc = subprocess.Popen("connmanctl services", stdout=subprocess.PIPE,shell=True)
        out=proc.communicate()[0].decode("utf-8")
        if name not in out:
               return 0 
        else:
               temp=out.split("\n")
               for a in temp:
                      if name in a:
                            a=re.sub(' +',' ',a)
                            wififound=a.split(" ")[2]
                            service_name="[service_"+wififound+"]"
                            ssid=wififound.split("_")[2]
                            break
        f = open("/var/lib/connman/ultra96.config", "w")
        f.write("%s\n"%service_name)
        f.write("Type=wifi\n")
        f.write("SSID=%s\n"%ssid)
        f.write("Passphrase=%s\n"%passphrase)
        connectcmd="connmanctl connect "+wififound
        os.system(connectcmd)
        return wififound


def createWiFi(output):
    open_ssid = []
    password_ssid = []
    ssid =False
    password = False
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("SSID"):
            ssid_list = line.split(": ")
            if len(ssid_list) == 2:
                ssid_name = ssid_list[1]
            ssid = True
        elif line.startswith("RSN"):
            password = True
        elif line.startswith("BSS"):
            if ssid and password:
                password_ssid.append(ssid_name)
            if ssid and not password: 
                open_ssid.append(ssid_name)
            ssid =  False
            password = False
    return (open_ssid, password_ssid)

@app.route('/information.html')
def specifications():
    files_found = []
    files = [os.path.basename(f) for f in glob.glob(CUR_DIRECTORY+'/static/documents/*')]
    for f in files:
        if f.lower().endswith(('.html', '.pdf')):
            files_found.append(f)
    return render_template("Information/information.html", files=files_found)

@app.route('/webapp_boot.html', methods=['GET', 'POST'])
def webapp_boot():
    if request.method == 'POST':
        if ('Yes' in request.form['optradio']):
            f = open(CUR_DIRECTORY+'/static/ultra96-startup-page.conf', 'w')
            f.write("webapp_on_boot=1\n")
            f.close()
            return render_template("Configurations/webapp_boot.html", boot="block", not_boot="none")
        else:
            f = open(CUR_DIRECTORY+'/static/ultra96-startup-page.conf', 'w')
            f.write("webapp_on_boot=0\n")
            f.close()
            return render_template("Configurations/webapp_boot.html", boot="none", not_boot="block")
    else:    
        return render_template("Configurations/webapp_boot.html", boot="none", not_boot="none")

@app.route('/wifi_setup.html', methods=['GET', 'POST'])
def wifi_setup():
    wificonnected=""
    is_connected = check_connection()
    if request.method == 'POST':
        if 'ssid' in request.form:
            ssid = request.form['ssid']
            passphrase = ""
            if 'password' in request.form:
                passphrase = request.form['password']
            if os.path.exists("/etc/wpa_supplicant.conf"):
                p = subprocess.call("mv /etc/wpa_supplicant.conf /etc/wpa_supplicant.conf.old", stdout=subprocess.PIPE, shell=True)
                if p != 0:
                    success = "none"
                    return render_template("Configurations/wifi_setup.html", open_ssid=[], password_ssid=[], connected=is_connected, success="none", failure="block", con_pass="none", con_fail="none", ssid="")        
            
            wificonnected=connect_to_wifi(ssid,passphrase)
            if wificonnected == 0:
                    success = "none"		
                    return render_template("Configurations/wifi_setup.html", open_ssid=[], password_ssid=[], connected=is_connected, success="none", failure="block", con_pass="none", con_fail="none", ssid="")        

            return render_template("Configurations/wifi_setup.html", open_ssid=[], password_ssid=[], connected=is_connected, success="block", failure="none", con_pass="none", con_fail="none", ssid="")
        elif 'refresh' in request.form:
            os.system("ip link set dev wlan0 up")
            i = 0 
            while i < 5:
                i = i+1
                p = subprocess.Popen("iw wlan0 scan", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                output_encoded, err = p.communicate()
                output=output_encoded.decode('utf-8')
                if "SSID" in output:
                    open_ssid, password_ssid = createWiFi(output)
                    #os.system("ip link set dev wlan0 down")
                    return render_template("Configurations/wifi_setup.html", open_ssid=open_ssid, password_ssid=password_ssid, connected=is_connected, success="none", failure="none", con_pass="none", con_fail="none", ssid="")
            return render_template("Configurations/wifi_setup.html", open_ssid=[], password_ssid=[], connected=is_connected, success="none", failure="none", con_pass="none", con_fail="none", ssid="")
        elif 'disconnect' in request.form:
            f=open("/var/lib/connman/ultra96.config","r")
            out=f.readline()
            wificonnected=out.split("service_")[1].split("]")[0]
            disconnectcmd="connmanctl disconnect "+wificonnected
            print("wificonnected=%s"%wificonnected)
            os.system(disconnectcmd)
            is_connected = check_connection()
            return render_template("Configurations/wifi_setup.html", open_ssid=[], password_ssid=[], connected=is_connected, success="none", failure="none", con_pass="none", con_fail="none", ssid="")            
        else:
            p = subprocess.Popen("iw wlan0 info", stdout=subprocess.PIPE, shell=True)
            ssid_output_encoded = p.communicate()[0]
            ssid_output = ssid_output_encoded.decode('utf-8')
            ssid = ""
            for line in ssid_output.splitlines():
                line.strip()
                if "ssid" in line:
                    ssid = line.split("ssid ")[1]
            if ssid == "":
                return render_template("Configurations/wifi_setup.html", open_ssid=[], password_ssid=[], connected=is_connected, success="none", failure="none", con_pass="none", con_fail="block", ssid="")
            return render_template("Configurations/wifi_setup.html", open_ssid=[], password_ssid=[], connected=is_connected, success="none", failure="none", con_pass="block", con_fail="none", ssid=ssid_output)
    else:
        return render_template("Configurations/wifi_setup.html", open_ssid=[], password_ssid=[], connected=is_connected, success="none", failure="none", con_pass="none", con_fail="none", ssid="")

@app.route('/configurations.html')
def configurations():
    return render_template("Configurations/configurations.html")

@app.route('/password.html', methods=['GET', 'POST'])
def password():
    success = "block"
    failure = "none"
    if request.method == 'POST':
        oldpass = request.form['oldpassword']
        newpass = request.form['newpassword']
        p = subprocess.Popen("cat /etc/shadow", stdout=subprocess.PIPE, shell=True)
        root_salt = p.communicate()[0].split(":", 2)[1]
        if root_salt == "x" or root_salt == "*" or root_salt == "!":
            success = "none"
            failure = "block"
            return render_template("Configurations/password.html", success=success, failure=failure)
        if (crypt.crypt(oldpass, root_salt) == root_salt) or (root_salt=="" and crypt.crypt(oldpass, root_salt) == None):
            #Create random salt
            salt_set = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "/"]
            random_salt = "".join(random.choice(salt_set) for index in range(32))
            encrypted_password = crypt.crypt(newpass, random_salt)
            p = subprocess.call("usermod -p "+encrypted_password+" root", stdout=subprocess.PIPE, shell=True)
            if p != 0:
                success = "none"
                failure = "block"
            return render_template("Configurations/password.html", success=success, failure=failure)
        else:
            success = "none"
            failure = "block"
            return render_template("Configurations/password.html", success=success, failure=failure)
    else:
        success = "none"
        return render_template("Configurations/password.html", success=success, failure=failure)

@app.route('/dnf_update.html', methods=['GET', 'POST'])
def dnf_update():
    if request.method == 'POST':
        p = subprocess.Popen("iw wlan0 info | grep ssid", stdout=subprocess.PIPE, shell=True)
        ssid_output = p.communicate()[0]
        if ssid_output != "":
            os.system("dnf repoquery")
            if "96boards" in request.form:
                os.system("dnf install -y "+request.form["96boards"])
            if "audio" in request.form:
                os.system("dnf install -y "+request.form["audio"])
            if "benchmarks" in request.form:
                os.system("dnf install -y "+request.form["benchmarks"])
            if "gstreamer" in request.form:
                os.system("dnf install -y "+request.form["gstreamer"])
            if "mraa" in request.form:
                os.system("dnf install -y "+request.form["mraa"])
            if "openamp" in request.form:
                os.system("dnf install -y "+request.form["openamp"])
            if "opencv" in request.form:
                os.system("dnf install -y "+request.form["opencv"])
            if "qt" in request.form:
                os.system("dnf install -y "+request.form["qt"])
            if "x11" in request.form:
                os.system("dnf install -y "+request.form["x11"])
            if "xfce" in request.form:
                os.system("dnf install -y "+request.form["xfce"])
            if "startup" in request.form:
                os.system("dnf install -y "+request.form["startup"])
            if "petalinux" in request.form:
                os.system("dnf install -y "+request.form["petalinux"])
            if "self" in request.form:
                os.system("dnf install -y "+request.form["self"])
            return render_template("Configurations/dnf_update.html", updates_done="block", no_wifi="none")
        else:
            return render_template("Configurations/dnf_update.html", updates_done="none", no_wifi="block")
    else:
        return render_template("Configurations/dnf_update.html", updates_done="none", no_wifi="none")

@app.route('/Ultra96_LEDs.html', methods=['GET', 'POST'])
def ultra96_leds():
    if request.method == 'POST':
        post_Ultra96_leds(request.form['led'], request.form['trigger'])
    return render_template("Projects/Ultra96_LEDs.html", triggers=triggers, leds=leds)

@app.route('/projects.html')
def projects():
    return render_template("Projects/projects.html")

@app.route('/hello_world.html', methods=['GET', 'POST'])
def hello_world():
    global timeout
    global timer_status
    global elapsed_time
    global runme_proc 

    if request.method == 'POST':
        if request.form['timeout']:
          timeout = request.form['timeout']
         
        if request.form['submit'] == 'stop':
           os.killpg(os.getpgid(runme_proc.pid),signal.SIGTERM)
           timer_status="timer_disabled"
           return render_template("Projects/hello_world.html", timeout=timeout, remaining_time=timeout, timer_status=timer_status)
      
        timer_status = "timer_enabled"
        os.chdir("/usr/share/Sensor_Mezzanine_Getting_Started/rgb_lcd_demo/")
        runme_proc = subprocess.Popen("sh run_me.sh", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, preexec_fn=os.setpgrp)
        multiprocessing.Process(target=thread_run, args=(runme_proc, timeout, cconn)).start()
        os.chdir(CUR_DIRECTORY)
        return render_template("Projects/hello_world.html", timeout=timeout, remaining_time=timeout, timer_status=timer_status)
    
    while(pconn.poll()):
        val = pconn.recv()
        elapsed_time = val
    elapsed_time = int(elapsed_time)
    timeout = int(timeout)
    remaining_time = timeout - elapsed_time
    return render_template("Projects/hello_world.html", timeout=timeout, remaining_time=remaining_time, timer_status=timer_status)

@app.route('/touch_sensor.html', methods=['GET', 'POST'])
def touch_sensor():
    global timeout
    global timer_status
    global elapsed_time
    global runme_proc 

    if request.method == 'POST':
        if request.form['timeout']:
          timeout = request.form['timeout']

        if request.form['submit'] == 'stop':
           os.killpg(os.getpgid(runme_proc.pid),signal.SIGTERM)
           timer_status="timer_disabled"
           return render_template("Projects/touch_sensor.html", timeout=timeout, remaining_time=timeout, timer_status=timer_status)

        timer_status = "timer_enabled"
        os.chdir("/usr/share/Sensor_Mezzanine_Getting_Started/touch_switch/")
        runme_proc = subprocess.Popen("sh run_me.sh", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, preexec_fn=os.setpgrp)
        multiprocessing.Process(target=thread_run, args=(runme_proc, timeout, cconn)).start()
        os.chdir(CUR_DIRECTORY)
        return render_template("Projects/touch_sensor.html", timeout=timeout, remaining_time=timeout, timer_status=timer_status)

    while(pconn.poll()):
        val = pconn.recv()
        elapsed_time = val
    elapsed_time = int(elapsed_time)
    timeout = int(timeout)
    remaining_time = timeout - elapsed_time
    return render_template("Projects/touch_sensor.html", timeout=timeout, remaining_time=remaining_time, timer_status=timer_status)

@app.route('/led_button.html', methods=['GET', 'POST'])
def led_button():
    if request.method == 'POST':
        os.chdir("/usr/share/Sensor_Mezzanine_Getting_Started/button_led/")
        runme_proc = subprocess.Popen("sh run_me.sh", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        os.chdir(CUR_DIRECTORY)
    return render_template("Projects/led_button.html")

@app.route('/buzz_light_sensor.html', methods=['GET', 'POST'])
def buzz_light_sensor():
    if request.method == 'POST':
        os.chdir("/usr/share/Sensor_Mezzanine_Getting_Started/light_buzz/")
        runme_proc = subprocess.Popen("sh run_me.sh", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        os.chdir(CUR_DIRECTORY)
    return render_template("Projects/buzz_light_sensor.html")

@app.route('/tweeting_doorbell.html', methods=['GET', 'POST'])
def tweeting_doorbell():
    global timeout
    global timer_status
    global elapsed_time
    global runme_proc
    
    if request.method == 'POST':
        if request.form['submit'] == 'stop':
           os.killpg(os.getpgid(runme_proc.pid),signal.SIGTERM)
           timer_status="timer_disabled"
           return render_template("Projects/tweeting_doorbell.html", timeout=timeout, remaining_time=timeout, timer_status=timer_status)

        if request.form['submit'] == 'key_val':
            usr_key = request.form["usr_key"]
            usr_secret = request.form["usr_secret"]
            usr_token = request.form["usr_token"]
            usr_token_secret = request.form["usr_token_secret"]
            f = open("/usr/share/Sensor_Mezzanine_Getting_Started/tweeting_doorbell/keys.py", "w")
            f.write("consumer_key = \"" +usr_key + "\"\n")
            f.write("consumer_secret = \"" +usr_secret + "\"\n")
            f.write("access_token = \"" +usr_token + "\"\n")
            f.write("access_token_secret = \"" +usr_token_secret + "\"\n")
            f.close()
            return render_template("Projects/tweeting_doorbell.html", usr_key=usr_key, usr_secret=usr_secret, usr_token=usr_token, usr_token_secret=usr_token_secret, timeout=timeout, remaining_time=timeout, timer_status=timer_status, twitter="", missing_keys="none")
        timeout = request.form['timeout']
        timer_status = "timer_enabled"
        os.chdir("/usr/share/Sensor_Mezzanine_Getting_Started/tweeting_doorbell/")
    
        if os.path.exists("/usr/share/Sensor_Mezzanine_Getting_Started/tweeting_doorbell/keys.py"):
            runme_proc = subprocess.Popen("sh run_me.sh "+request.form["twitter"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, preexec_fn=os.setpgrp)
            output = ""
            while "flash:w:build-uno/tweeting_doorbell.hex" not in output :
                output = runme_proc.stdout.readline().decode('utf-8')
            timer_status = "timer_enabled"
            multiprocessing.Process(target=thread_run, args=(runme_proc, timeout, cconn)).start()
            os.chdir(CUR_DIRECTORY)
            return render_template("Projects/tweeting_doorbell.html", timeout=timeout, remaining_time=timeout, timer_status=timer_status, twitter=request.form["twitter"], missing_keys="none")
        else:
            return render_template("Projects/tweeting_doorbell.html", timeout=timeout, remaining_time=timeout, timer_status=timer_status, twitter=request.form["twitter"], missing_keys="block")
    while(pconn.poll()):
        val = pconn.recv()
        elapsed_time = val
    elapsed_time = int(elapsed_time)
    timeout = int(timeout)
    remaining_time = timeout - elapsed_time
    return render_template("Projects/tweeting_doorbell.html", timeout=timeout, remaining_time=remaining_time, timer_status=timer_status, twitter="notweet", missing_keys="none")

@app.route('/temp_display.html', methods=['GET', 'POST'])
def temp_display():
    global timeout
    global timer_status
    global elapsed_time
    global runme_proc

    if request.method == 'POST':
        if request.form['timeout']:
          timeout = request.form['timeout']

        if request.form['submit'] == 'stop':
           os.killpg(os.getpgid(runme_proc.pid),signal.SIGTERM)
           timer_status="timer_disabled"
           return render_template("Projects/temp_display.html", timeout=timeout, remaining_time=timeout, timer_status=timer_status)

        os.chdir("/usr/share/Sensor_Mezzanine_Getting_Started/humid_temp/")
        runme_proc = subprocess.Popen("sh run_me.sh", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, preexec_fn=os.setpgrp)
        output = ""
        while "flash:w:build-uno/humid_temp.hex" not in output:
             output = runme_proc.stdout.readline().decode('utf-8')
        timer_status = "timer_enabled"
        multiprocessing.Process(target=thread_run, args=(runme_proc, timeout, cconn)).start()
        os.chdir(CUR_DIRECTORY)
        return render_template("Projects/temp_display.html", timeout=timeout, remaining_time=timeout, timer_status=timer_status)
    
    while(pconn.poll()):
        val = pconn.recv()
        elapsed_time = val
    elapsed_time = int(elapsed_time)
    timeout = int(timeout)
    remaining_time = timeout - elapsed_time
    return render_template("Projects/temp_display.html", timeout=timeout, remaining_time=remaining_time, timer_status=timer_status)

@app.route('/viewer.html', methods=['GET', 'POST'])
def viewer():
    global timeout
    global timer_status
    global elapsed_time
    if request.method == 'POST':
        if "revert" in request.form:
            code = "ERROR: Could not find file"
            if os.path.exists("/usr/share/Sensor_Mezzanine_Getting_Started"+request.args.get('filename')+".bak"):
                if os.path.exists("/usr/share/Sensor_Mezzanine_Getting_Started/"+request.args.get('filename')):
                    with open("/usr/share/Sensor_Mezzanine_Getting_Started/"+request.args.get('filename')+".bak", "r") as f:
                        code = f.read()
                    f.close()
                    f = open("/usr/share/Sensor_Mezzanine_Getting_Started/"+request.args.get('filename'), "w")
                    f.write(code)
                    f.close()
            return render_template("Projects/viewer.html", code=code, filename=os.path.basename(request.args.get('filename')), log="No log data. Run code to get log data")
        code = request.form['code']
        if request.form['request'] == 'save':
            f = open("/usr/share/Sensor_Mezzanine_Getting_Started/"+request.args.get('filename'), "w")
            f.write(request.form['code'])
            f.close()
            return render_template("Projects/viewer.html", code=code, filename=os.path.basename(request.args.get('filename')), log="No log data. Run code to get log data")
        else:
            f = open("/usr/share/Sensor_Mezzanine_Getting_Started/"+request.args.get('filename'), "w")
            f.write(request.form['code'])
            f.close()
            os.chdir("/usr/share/Sensor_Mezzanine_Getting_Started/"+os.path.dirname(request.args.get('filename')))
            timer_status = "timer_enabled"
            runme_proc = subprocess.Popen("sh run_me.sh", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, preexec_fn=os.setpgrp)
            multiprocessing.Process(target=thread_run, args=(runme_proc, timeout, cconn)).start()
            os.chdir(CUR_DIRECTORY)
            output, err = runme_proc.communicate()
            return render_template("Projects/viewer.html", code=code, filename=os.path.basename(request.args.get('filename')), log=output.decode('utf-8')+"\n"+err.decode('utf-8'))
    else:
        code = "ERROR: Could not find file"
        if os.path.exists("/usr/share/Sensor_Mezzanine_Getting_Started/"+request.args.get('filename')):
            with open("/usr/share/Sensor_Mezzanine_Getting_Started/"+request.args.get('filename'), "r") as f:
                code = f.read()
            f.close()
        while(pconn.poll()):
            val = pconn.recv()
            elapsed_time = val
        remaining_time = int(timeout) - int(elapsed_time)
        return render_template("Projects/viewer.html", code=code, filename=os.path.basename(request.args.get('filename')), timeout=timeout, remaining_time=remaining_time, timer_status=timer_status, log="No log data. Run code to get log data")

@app.route('/iperf3_s.html', methods=['GET', 'POST'])
def iperf3_s():
    if request.method == 'POST':
        #Start the iperf3 server to run and stop after the first connection finishes
        os.system("iperf3 -s -i 2 -1 > /home/root/iperf3_s_results.txt")
        output = ""
        with open("/home/root/iperf3_s_results.txt","r") as file:
            output = file.read()

        return render_template("Projects/iperf3_s.html", output=output)
    else:
        return render_template("Projects/iperf3_s.html", output="")

@app.route('/iperf3_c.html', methods=['GET', 'POST'])
def iperf3_c():
    if request.method == 'POST':
        #Fetch the IP address of the remote PC that is running the iperf3 server
        IP_addr = request.environ['REMOTE_ADDR']
      
        #Start the iperf3 client to update every 2 seconds and stop after 20 seconds
        os.system("iperf3 -c " +IP_addr+ " -i 2 -t 20 > /home/root/iperf3_c_results.txt")

        output = ""
        with open("/home/root/iperf3_c_results.txt","r") as file:
            output = file.read()

        return render_template("Projects/iperf3_c.html", output=output)
    else:
        return render_template("Projects/iperf3_c.html", output="")

@app.route('/echo_test.html', methods=['GET', 'POST'])
def echo_test():
    if request.method == 'POST':
        os.system("echo image_echo_test > /sys/class/remoteproc/remoteproc0/firmware")
        os.system("echo start > /sys/class/remoteproc/remoteproc0/state")
        os.system("modprobe rpmsg_char")
        os.system("echo_test > /home/root/echo_results.txt")
        output = ""
        with open("/home/root/echo_results.txt","r") as file:
            output = file.read()

        os.system("modprobe -r rpmsg_char")
        os.system("echo stop > /sys/class/remoteproc/remoteproc0/state")

        return render_template("Projects/echo_test.html", output=output)
    else:
        return render_template("Projects/echo_test.html", output="")

@app.route('/matrix_mult.html', methods=['GET', 'POST'])
def matrix_mult():
    if request.method == 'POST':
        os.system("echo image_matrix_multiply > /sys/class/remoteproc/remoteproc0/firmware")
        os.system("echo start > /sys/class/remoteproc/remoteproc0/state")
        os.system("modprobe rpmsg_char")
        os.system("mat_mul_demo > /home/root/mat_mul_results.txt")
        output = ""
        with open("/home/root/mat_mul_results.txt","r") as file:
            output = file.read()

        os.system("modprobe -r rpmsg_char")
        os.system("echo stop > /sys/class/remoteproc/remoteproc0/state")

        return render_template("Projects/matrix_mult.html", output=output)
    else:
        return render_template("Projects/matrix_mult.html", output="")

@app.route('/proxy_app.html', methods=['GET', 'POST'])
def proxy_app():
    if request.method == 'POST':
        username = request.form['username']
        age = request.form['age']
        pi = request.form['pi']

        with open("/home/root/proxy_input.txt","w") as file:
            file.write(str(username + "\n"))
            file.write(str(age + "\n"))
            file.write(str(pi + "\n"))
            file.write(str("no\n"))
            
        os.system("proxy_app < /home/root/proxy_input.txt > /home/root/proxy_results.txt")

        output = ""
        with open("/home/root/proxy_results.txt","r") as file:
            output = file.read()

        os.system("rm /home/root/remote.file")

        return render_template("Projects/proxy_app.html", output=output)
    else:
        return render_template("Projects/proxy_app.html", output="")

@app.route('/tutorials.html')
def tutorials():    
    return render_template("Tutorials/tutorials.html")

@app.route('/dnf.html')
def dnf():
    return render_template("Tutorials/dnf.html")

@app.route('/grove_starter_kit.html')
def grove_starter_kit():
    return render_template("Tutorials/grove_starter_kit.html")

@app.route('/custom_content_tutorial.html')
def guide_custom_projects():
    return render_template("Tutorials/custom_content_tutorial.html")

@app.route('/run_project_tutorial.html')
def run_project_tutorial():
    return render_template("Tutorials/run_project_tutorial.html")    

@app.route('/using_ultra96.html')
def using_ultra96():
    return render_template("Tutorials/using_ultra96.html")

@app.route('/customcontent.html', methods=['GET', 'POST'])
def customcontent():
    from werkzeug.utils import secure_filename
    uploaded_files =  [os.path.basename(f) for f in glob.glob(CUR_DIRECTORY+"/templates/CustomContent/uploaded_files/*")]
    custom_files = [os.path.basename(f) for f in glob.glob(CUR_DIRECTORY+"/templates/CustomContent/custom/*")]
    included_files = []
    included_read = ""
    if os.path.exists(CUR_DIRECTORY+"/templates/CustomContent/custom_front_end/files_included.conf"):
        with open(CUR_DIRECTORY+"/templates/CustomContent/custom_front_end/files_included.conf", "r") as f:
            included_read = f.read()
        f.close()
    included_check = included_read.split(" ")
    for filename in included_check:
        if os.path.exists(CUR_DIRECTORY+"/templates/CustomContent/custom_front_end/"+filename+".html"):
            included_files.append(filename)

    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template("CustomContent/customcontent.html", docs=uploaded_files, file_bad="block", file_good="none", proj=custom_files, webapp_include=included_files)
        upload = request.files['file']
        if upload.filename == '':
            return render_template("CustomContent/customcontent.html", docs=uploaded_files, file_bad="block", file_good="none", proj=custom_files, webapp_include=included_files)
        if upload:
            filename = secure_filename(upload.filename)
            upload.save(os.path.join(CUR_DIRECTORY+'/templates/CustomContent/uploaded_files/', filename))   
            if filename not in uploaded_files:
                uploaded_files.append(filename)
            return render_template("CustomContent/customcontent.html", docs=uploaded_files, file_bad="none", file_good="block", proj=custom_files, webapp_include=included_files)
        else:
            return render_template("CustomContent/customcontent.html", docs=uploaded_files, file_bad="block", file_good="none", proj=custom_files, webapp_include=included_files)
    else:
        if request.args.get('delete_uploaded') is not None:
            if os.path.exists(CUR_DIRECTORY+"/templates/CustomContent/uploaded_files/"+request.args.get('delete_uploaded')):
                os.remove(CUR_DIRECTORY+"/templates/CustomContent/uploaded_files/"+request.args.get('delete_uploaded'))
            if request.args.get('delete_uploaded') in uploaded_files:
                uploaded_files.remove(request.args.get('delete_uploaded'))
        elif request.args.get('delete_proj') is not None:
            if os.path.exists(CUR_DIRECTORY+"/templates/CustomContent/custom/"+request.args.get('delete_proj')):
                os.remove(CUR_DIRECTORY+"/templates/CustomContent/custom/"+request.args.get('delete_proj'))
            if request.args.get('delete_proj') in custom_files:
                custom_files.remove(request.args.get('delete_proj'))
        return render_template("CustomContent/customcontent.html", docs=uploaded_files, file_bad="none", file_good="none", proj=custom_files, webapp_include=included_files)


@app.route('/custom_front_end.html', methods=['GET', 'POST'])
def custom_front_end():
    if request.method == 'POST':
        code = request.form['code']
        if request.form['request'] == 'save':
            filename = request.form['filename_form']+".html"
            f = open(CUR_DIRECTORY+"/templates/CustomContent/custom_front_end/"+filename, "w")
            f.write(request.form['code'])
            f.close()
            return render_template("CustomContent/custom_front_end.html", fileexists="none", filecreated="block", code=code, filename=filename)
    else:
        code = ('<!--\n'
                '- The following will briefly explain how to edit code on this page.\n'
                '- For a more in depth explanation go to the tutorial page and select "Custom Front End".\n'
                '- This is an HTML file and the navbar and footer will already be included along with some other fancy things.\n'
                '- Add code in the sections where it mentions to add code below.\n'
                '- Change "CHANGE ME" to your own desired name to show up for this webpage.\n'
                '- Good luck!\n'
                '-->\n'
                '\n'
                '{% extends "Default/default.html" %}\n'
                '{% block content %}\n'
                '\n'
                '<div class="page-header">\n'
                '  <h1 class="display-4"><b>{% block title %}CHANGE ME{% endblock %}</b></h1>\n'
                '</div>\n'
                '\n'
                '<!-- Start adding your code below here -->\n'
                '\n'
                '\n'
                '\n'
                '\n'
                '\n'
                '<!-- Stop adding your code here -->\n'
                '\n'
                '{% endblock %}\n')

        if request.args.get('filename') is not None:
            with open(CUR_DIRECTORY+"/templates/CustomContent/custom_front_end/"+request.args.get('filename'), "r") as f:
                code = f.read()
            f.close()
            return render_template("CustomContent/custom_front_end.html", fileexists="none", filecreated="none", code=code, filename=request.args.get('filename'))
        return render_template("CustomContent/custom_front_end.html", fileexists="none", filecreated="none", code=code, filename="Unsaved File")

@app.route('/custom_back_end.html', methods=['GET', 'POST'])
def custom_back_end():
    if request.method == 'POST':
        code = request.form['code']
        if request.form['request'] == 'save':
            filename = request.form['filename_form']+".py"
            f = open(CUR_DIRECTORY+"/templates/CustomContent/custom_back_end/"+filename, "w")
            f.write(request.form['code'])
            f.close()
            return render_template("CustomContent/custom_back_end.html", fileexists="none", filecreated="block", code=code, filename=filename)
    else:
        code = ('#The following will briefly explain how to edit code on this page\n'
                '#For more information go to the Tutorial page and select the "Custom Back End" tutorial\n'
                '#Make sure to change "CHANGE ME" to be the name that was given to the file on the first 2 lines of this python code\n'
                '#Good luck and have fun!\n'
                '\n'
                '@app.route("/CHANGE_ME.html", methods=["GET", "POST"])\n'
                'def CHANGE_ME():\n'
                '    if request.method == "POST":\n'
                '        return render_template("CustomContent/custom_front_end/CHANGE_ME.html")\n'
                '    else:\n'
                '        return render_template("CustomContent/custom_front_end/CHANGE_ME.html")\n')
        if request.args.get('filename') is not None:
            with open(CUR_DIRECTORY+"/templates/CustomContent/custom_back_end/"+request.args.get('filename'), "r") as f:
                code = f.read()
            f.close()
            return render_template("CustomContent/custom_back_end.html", fileexists="none", filecreated="none", code=code, filename=request.args.get('filename'))
        return render_template("CustomContent/custom_back_end.html", fileexists="none", filecreated="none", code=code, filename="Unsaved File")

@app.route('/editor.html', methods=['GET', 'POST'])
def editor():
    output = ""
    if request.method == 'POST':
        code = request.form['code']
        if request.form['request'] == 'save':
            filename = request.form['filename_form']
            if request.args.get('filename') is not None:
                if request.args.get('filename') == filename:
                    f = open(CUR_DIRECTORY+"/templates/CustomContent/custom/"+filename, "w")
                    f.write(request.form['code'])
                    f.close()
                    return render_template("CustomContent/editor.html", fileexists="none", filecreated="block", output=output, code=code, filename=filename)
            if os.path.exists(CUR_DIRECTORY+"/templates/CustomContent/custom/"+filename):
                return render_template("CustomContent/editor.html", fileexists="block", filecreated="none", output=output, code=code, filename=filename)
            else:
                f = open(CUR_DIRECTORY+"/templates/CustomContent/custom/"+filename, "w")
                f.write(request.form['code'])
                f.close()
                return render_template("CustomContent/editor.html", fileexists="none", filecreated="block", output=output, code=code, filename=filename)
        else:
            if request.args.get('filename') is not None:
                if request.args.get('filename').lower().endswith(('.py')):
                    f = open(CUR_DIRECTORY+"/templates/CustomContent/temp/temp.py", "w")
                    f.write(request.form['code'])
                    f.close()
                    p = subprocess.Popen("python "+CUR_DIRECTORY+"/templates/CustomContent/temp/temp.py", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                    output,err = p.communicate()
                    if p.returncode != 0:
                        output = ("ERROR:\n%s" % err)
                    os.remove(CUR_DIRECTORY+"/templates/CustomContent/temp/temp.py")
                else:
                    output = "ERROR:\nCan only run Python files (ending in .py)"
                return render_template("CustomContent/editor.html", fileexists="none", filecreated="none", output=output, code=code, filename=request.args.get('filename'))
            else:
                f = open(CUR_DIRECTORY+"/templates/CustomContent/temp/temp.py", "w")
                f.write(request.form['code'])
                f.close()
                p = subprocess.Popen("python "+CUR_DIRECTORY+"/templates/CustomContent/temp/temp.py", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                output,err = p.communicate()
                if p.returncode != 0:
                    output = ("ERROR:\n%s" % err)
                os.remove(CUR_DIRECTORY+"/templates/CustomContent/temp/temp.py")
            return render_template("CustomContent/editor.html", fileexists="none", filecreated="none", output=output, code=code, filename="Unsaved File")
    else:
        code = '#Sample Python Code\r\nprint "Hello World!"\r\n'
        if request.args.get('filename') is not None:
            if os.path.exists(CUR_DIRECTORY+"/templates/CustomContent/custom/"+request.args.get('filename')):
                with open(CUR_DIRECTORY+"/templates/CustomContent/custom/"+request.args.get('filename'), "r") as f:
                    code = f.read()
                f.close()
                if request.args.get('python') is not None:
                    p = subprocess.Popen("python "+CUR_DIRECTORY+"/templates/CustomContent/custom/"+request.args.get("filename"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                    output, err = p.communicate()
                    if p.returncode != 0:
                        output = ("ERROR:\n%s" % err)
            elif os.path.exists(CUR_DIRECTORY+"/static/custom/"+request.args.get('filename')):
                with open(CUR_DIRECTORY+"/static/custom/"+request.args.get('filename'), "r") as f:
                    code = f.read()
                f.close()
            return render_template("CustomContent/editor.html", fileexists="none", filecreated="none", output=output, code=code, filename=request.args.get('filename'))
        return render_template("CustomContent/editor.html", fileexists="none", filecreated="none", output=output, code=code, filename="Unsaved File")

@app.route('/uploaded_editor.html', methods=['GET', 'POST'])
def uploaded_editor():
    if request.method == 'POST':
        code = request.form['code']
        filename = request.form['filename_form']
        if os.path.exists(CUR_DIRECTORY+"/templates/CustomContent/uploaded_files/"+filename):
            f = open(CUR_DIRECTORY+"/templates/CustomContent/uploaded_files/"+filename, "w")
            f.write(code)
            f.close()
            return render_template("CustomContent/uploaded_editor.html", filesaved="block", filemissing="none", code=code, filename=filename)
        else:
            return render_template("CustomContent/uploaded_editor.html", filesaved="none", filemissing="block", code=code, filename=filename)
    else:
        code = "Could not read file"
        if os.path.exists(CUR_DIRECTORY+"/templates/CustomContent/uploaded_files/"+request.args.get('filename')):
            with open(CUR_DIRECTORY+"/templates/CustomContent/uploaded_files/"+request.args.get('filename'), "r",encoding="utf-8") as f:
                code = f.read()
            f.close()
        return render_template("CustomContent/uploaded_editor.html", filesaved="none", filemissing="none", filename=request.args.get('filename'), code=code)

@app.route('/reload_webapp.html', methods=['GET', 'POST'])
def reload_webapp():
    code = ""
    webapp_reload = "none"
    if request.method == 'POST':
        includes = ""
        if request.form["reload_button"] != "":
            includes = request.form["reload_button"].split(" ")
        f = open(CUR_DIRECTORY+"/templates/CustomContent/custom_front_end/files_included.conf", "w")
        f.write(request.form["reload_button"])
        f.close()
        for file_include in includes:
            if os.path.exists(CUR_DIRECTORY+"/templates/CustomContent/custom_front_end/"+file_include+".html"):
                if os.path.exists(CUR_DIRECTORY+"/templates/CustomContent/custom_back_end/"+file_include+".py"):
                    with open(CUR_DIRECTORY+"/templates/CustomContent/custom_back_end/"+file_include+".py", "rU") as f:
                        code = code + f.read()
                    f.close()
        os.system("cp "+CUR_DIRECTORY+"/webserver.py.bak "+CUR_DIRECTORY+"/webserver.py")
        with open(CUR_DIRECTORY+"/webserver.py", "a") as f:
            f.write("\n#CUSTOM USER BACK END CODE ADDED AFTER HERE\n\n")
            f.write(code)
            f.write("\n#CUSTOM USER BACK END CODE STOPS HERE\n\n")
            f.write("if __name__ == '__main__':\n")
            f.write("    app.run(host='0.0.0.0', port=80, threaded=True)\n")
        f.close()
        p = subprocess.Popen("sleep 5; reboot", shell=True) 
        webapp_reload = "block"
    else:
        if request.args.get('delete') is not None:
            if os.path.exists(CUR_DIRECTORY+"/templates/CustomContent/custom_front_end/"+request.args.get("delete")+".html"):
                os.system("rm "+CUR_DIRECTORY+"/templates/CustomContent/custom_front_end/"+request.args.get("delete")+".html");
            if os.path.exists(CUR_DIRECTORY+"/templates/CustomContent/custom_back_end/"+request.args.get("delete")+".py"):
                os.system("rm "+CUR_DIRECTORY+"/templates/CustomContent/custom_back_end/"+request.args.get("delete")+".py");
            
    frontend = []
    backend = []
    filelist = []
    for filename in os.listdir(CUR_DIRECTORY+"/templates/CustomContent/custom_front_end/"):
        if filename.endswith(".html"):
            frontend.append(filename)
    for filename in os.listdir(CUR_DIRECTORY+"/templates/CustomContent/custom_back_end/"):
        if filename.endswith(".py"):
            backend.append(filename)

    frontend = sorted(frontend)
    backend = sorted(backend)

    found_back = False
    for front_file in frontend:
        for back_file in backend:
            if front_file.split(".", 1)[0] == back_file.split(".", 1)[0]:
                filelist.append(front_file)
                filelist.append(back_file)
                found_back = True
                break
        if found_back:
            found_back = False
        else:
            filelist.append(front_file)
            filelist.append("N/A")

    for back_file in backend:
        if back_file in filelist:
            pass
        else:
            filelist.append("N/A")
            filelist.append(back_file)

    return render_template("CustomContent/reload_webapp.html", filelist=filelist, webapp_reload=webapp_reload)


def post_Ultra96_leds(led, trigger):
    trigger = int(trigger)
    with open(f'/sys/class/leds/{led}/trigger', "w") as trigger_file:
        trigger_file.write("none")
    with open(f'/sys/class/leds/{led}/{triggers[trigger].get("file")}', "w") as led_file:
        led_file.write(triggers[trigger].get('value'))

def thread_run(proc, timeout, cconn):
    timeout = int(timeout) #Convert string to int
    start_time = time.time()
    elapsed_time = time.time()-start_time
    while (timeout > elapsed_time) and (proc.poll() is not None):
        time.sleep(1)
        elapsed_time = time.time()-start_time
        if cconn:
            cconn.send(elapsed_time)
    if proc.poll() is not None:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)  
    output,err = proc.communicate()

def check_connection():
    p = subprocess.Popen("iw wlan0 info", stdout=subprocess.PIPE, shell=True)
    ssid_output_encoded = p.communicate()[0]
    ssid_output = ssid_output_encoded.decode('utf-8')
    ssid = ""
    for line in ssid_output.splitlines():
        line.strip()
        if "ssid" in line:
            ssid = line.split("ssid ")[1]

    if ssid != "":
        return "true"
    return "false"

#CUSTOM USER BACK END CODE ADDED AFTER HERE

#CUSTOM USER BACK END CODE STOPS HERE

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, threaded=True)
