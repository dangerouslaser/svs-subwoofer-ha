# pySVS

Graphical Python3 program (Tkinter) to control SVS SB-1000PRO Subwoofer parameters using bluetooth interface. Parameters "Volume", "Phase", Low Pass Filter","Room Gain Compensation" Parametric EQ and Presets are available.   
v3: Totally rewritten. Added Parametric EQ and Presets compatibility. Added command-line options
![GitHub Logo](https://raw.githubusercontent.com/logon84/pySVS/main/pic.png)  
  
```
    pySVS ' + VERSION + '. Read and set SVS SB1000P Subwoofer values. By Logon84 http://github.com/logon84
    Run pySVS.py without arguments to launch the GUI
    USAGE: pySVS.py <-b device> <-m MAC_Address> <parameter1> <value1> <parameter2> <value2> etc...
    -b dev or --btdevice=dev: Specify a different BT device to use (default is hci0).
    -m MAC or --mac=MAC: Sets a mac address different to the one set in pySVS.py file.
    -h or --help: Show this help.
    -v or --version: Show program version.
    -e or --encode: Just print built frames based on param values.
    -d FRAME or --decode=FRAME: Decode values of a frame.
    PARAMETER LIST:
    	-l X@Y@Z or --lpf=X@Y@Z: Sets Low Pass Filter to X[0(OFF),1(ON)], Y[freq] and Z[slope].
    	-q V@W@X@Y@Z or --peq=V@W@X@Y@Z: Sets PEQ V[1..3], W[0(OFF),1(ON)], X[freq], Y[boost] and Z[Qfactor].
    	-r X@Y@Z or --roomgain=X@Y@Z: Sets RoomGain X[0(OFF),1(ON)], Y[freq] and Z[slope].')
    	-o X or --volume=X: Sets volume level to X on subwoofer.
    	-f X or --phase=X: Sets phase level to X on subwoofer.
    	-k X or --polarity=X: Sets polarity to 0(+) or 1(-) on subwoofer.
    	-p X or --preset=X: Load preset X[1..4(FACTORY DEFAULT PRESET)] on subwoofer.
    	To ask subwoofer for one or more values, set parameter value to "A".
```
  
The program requires bleak module installed:  
```
pip3 install bleak
```

Before running the program, be sure to edit the pySVS.py file and enter the mac address of your SVS Subwoofer.

I only own a SB-1000PRO to test, so the rest of SVS Subwoofers could or couldn't work, I don't know. Tested on both Linux and Windows (version >= fall creators update).  
  
I take no responsibility on any damage or harm done with this program

[![Donate](https://www.paypalobjects.com/es_ES/ES/i/btn/btn_donateCC_LG.gif)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=ER2LTNM5LZDTY)  
BTC address: 12cQuFn7yMSfDB1uKPGKLMQ7XSj1XF2sVA
