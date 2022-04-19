# pySVS

Graphical Python3 program (Tkinter) to control SVS SB-1000PRO Subwoofer parameters using bluetooth interface. For the moment only parameters "Volume", "Phase", Low Pass Filter" and "Room Gain Compensation" are available.   

![alt text](https://i.imgur.com/hT6wXhO.png)

The program requires bleak module installed:  
```
pip3 install bleak
```

Before running the program, be sure to edit the pySVS.py file and enter the mac address of your SVS Subwoofer.

I only own a SB-1000PRO to test, so the rest of SVS Subwoofers could or couldn't work, I don't know. Tested on both Linux and Windows (version >= fall creators update).
