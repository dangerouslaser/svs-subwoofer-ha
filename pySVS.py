#!/usr/bin/python3 

from binascii import hexlify
import tkinter as tk
from tkinter import ttk
from PIL import ImageTk, Image
import time
import traceback
from threading import Thread
import requests
import sys
import asyncio
import platform
from bleak import BleakClient


#EDIT THIS VALUE#####################
SVS_MAC_ADDRESS = "01:23:45:67:89:AB"
#####################################

###################    SB-1000-PRO CONFIG    ###################

STEP = 2560

#SERV01 = "0000fef6-0000-1000-8000-00805f9b34fb"
#CHAR01 = "005f0005-2ff2-4ed5-b045-4c7463617865"
#CHAR02 = "005f0004-2ff2-4ed5-b045-4c7463617865"
#CHAR03 = "005f0003-2ff2-4ed5-b045-4c7463617865"
#CHAR04 = "005f0002-2ff2-4ed5-b045-4c7463617865"

#SERV02 = "1fee6acf-a826-4e37-9635-4d8a01642c5d"
#CHAR11 = "7691b78a-9015-4367-9b95-fc631c412cc6"  #change device name
CHAR12 = "6409d79d-cd28-479c-a639-92f9e1948b43"  #notification handle 0x12

#SERV03 = "0000180a-0000-1000-8000-00805f9b34fb"
#CHAR21 = "00002a29-0000-1000-8000-00805f9b34fb"
#CHAR22 = "00002a25-0000-1000-8000-00805f9b34fb"

#SERV04 = "00001801-0000-1000-8000-00805f9b34fb"
#CHAR31 = "00002a05-0000-1000-8000-00805f9b34fb"

SVS_COMMANDS = 	{
		"SET": b'\xaa\xf0\x1f\x11\x00', 
		"ASK": b'\xaa\xf1\x1f\x0f\x00'
		}
SVS_PARAMS = 	{
		"VOLUME": {"bin":b'\x04\x00\x00\x00\x2c\x00\x02', "limits": [-60,0], "limits_type":0, "reference": 0x1000000},
		"PHASE": {"bin":b'\x04\x00\x00\x00\x2e\x00\x02', "limits": [0,180], "limits_type":0, "reference": 0},
		"LOW_PASS_FILTER_ALL_SETTINGS":{"bin":b'\x04\x00\x00\x00\x08\x00\x06', "limits": ("LFE", "LOW_PASS_FILTER_FREQ","LOW_PASS_FILTER_SLOPE"), "limits_type":"combined", "reference": 0},
		"LFE":{"bin":b'\x04\x00\x00\x00\x08\x00\x02', "limits": [0,1], "limits_type":1, "reference": 0}, #[ON, OFF], discrete type
		"LOW_PASS_FILTER_FREQ":{"bin":b'\x04\x00\x00\x00\x0a\x00\x02', "limits": [30, 200], "limits_type":0, "reference": 0},
		"LOW_PASS_FILTER_SLOPE":{"bin":b'\x04\x00\x00\x00\x0c\x00\x02',"limits": [6, 12, 18, 24], "limits_type":1, "reference": 0}, #discrete type
		"ROOM_GAIN_ALL_SETTINGS":{"bin":b'\x04\x00\x00\x00\x26\x00\x06', "limits": ("ROOM_GAIN_ENABLE", "ROOM_GAIN_FREQ","ROOM_GAIN_SLOPE"), "limits_type":"combined", "reference": 0},
		"ROOM_GAIN_ENABLE":{"bin":b'\x04\x00\x00\x00\x26\x00\x02', "limits": [1,0], "limits_type":1, "reference": 0}, #[ON, OFF], discrete type
		"ROOM_GAIN_FREQ":{"bin":b'\x04\x00\x00\x00\x28\x00\x02', "limits": [25, 31, 40], "limits_type":1, "reference": 0}, #discrete type
		"ROOM_GAIN_SLOPE":{"bin":b'\x04\x00\x00\x00\x2a\x00\x02', "limits": [6,12], "limits_type":1, "reference": 0}, #discrete type
		"POWER_SETTING":{"bin":b'\x04\x00\x00\x00\x04\x00\x02', "limits": [0,2], "limits_type":0, "reference": 0}
		}

###################    End SB-1000-PRO CONFIG    ###################

###################    Bleak Routines    ###################

RUN_THREAD = True
PARTIAL_FRAME=b''
crc_error = False

def notification_handler(handle, data):
	#Everything that the svs subwoofer sends to us comes to this callback
	global PARTIAL_FRAME
	global crc_error
	if data[0] == 0xAA:
	#detected a frame start. Start building frame
		if crc_error == True:
		#crc_error was not reset before, print crc error and show PREVIOUS wrong frame
			print("Data with CRC missmatch received: " + str(hexlify(PARTIAL_FRAME)))
		PARTIAL_FRAME = data
	else:
	#detected a frame fragment. Add it to the previous partial frame
		PARTIAL_FRAME = PARTIAL_FRAME + data

	if PARTIAL_FRAME[len(PARTIAL_FRAME)-2:] == checksum_calc(PARTIAL_FRAME[:len(PARTIAL_FRAME)-2]):
		crc_error = False
		FULL_FRAME = PARTIAL_FRAME
		refresh_widgets(svs_decode(FULL_FRAME))
	else:
		crc_error = True

def threading():
	# Call function
	t1=Thread(target=bleak_device)
	t1.start()

def bleak_device():
	ADDRESS = (
	SVS_MAC_ADDRESS
	if platform.system() != "Darwin"
	else "B9EA5233-37EF-4DD6-87A8-2A875E821C46"
	)
	asyncio.run(gatt_thread(ADDRESS, CHAR12))

async def gatt_thread(address, char_uuid):
	async with BleakClient(address) as client:
		print(f"Connected: {client.is_connected}")

		#print services
		svcs = await client.get_services()
		for service in svcs:
			print("SERVICE: " + str(service))
			for char in service.characteristics:
				print("\tCHARACTERISTIC: " + str(char))
			print("")
		#subscribe to svs parameters characteristic
		await client.start_notify(char_uuid, notification_handler)

		#ask subwoofer for config
		await client.write_gatt_char(char_uuid, svs_encode("ASK", "VOLUME"))
		await asyncio.sleep(0.1)
		await client.write_gatt_char(char_uuid, svs_encode("ASK", "PHASE"))
		await asyncio.sleep(0.1)
		await client.write_gatt_char(char_uuid, svs_encode("ASK", "LOW_PASS_FILTER_ALL_SETTINGS"))
		await asyncio.sleep(0.1)
		await client.write_gatt_char(char_uuid, svs_encode("ASK", "ROOM_GAIN_ALL_SETTINGS"))
		await asyncio.sleep(0.1)

		while RUN_THREAD:
		#don't let this method die in order to RX continuosly
			if len(TX.BUFFER) > 0: 
				await client.write_gatt_char(char_uuid, TX.BUFFER)
				TX.BUFFER = ""
			await asyncio.sleep(0.2)
		print("Bleak Client Thread closed")

###################    End Bleak Routines    ###################

###################    SVS Frame Routines    ###################

def svs_encode(command, param, data=0):
	if command == 'SET':
		encoded_data = (STEP*int(data) + SVS_PARAMS[param]["reference"]).to_bytes(4, 'little')[:3]
	else:
		encoded_data = int(data).to_bytes(1, 'little')
	frame = SVS_COMMANDS[command] + SVS_PARAMS[param]["bin"] + encoded_data
	frame = frame + checksum_calc(frame)
	print("-> " + command + " " + param + " " + str(data) + " [" + str(hexlify(frame)) + "]")
	return frame

def svs_decode(frame):
	decoded_values = {}
	if len(frame) == 35:
	#multidata frame
		val_1 = 16*16*16*16*frame[18] + 16*16*frame[17] + frame[16]
		val_2 = 16*16*16*16*frame[20] + 16*16*frame[19] + frame[18]
		val_3 = 16*16*frame[21]
		values = [val_1, val_2, val_3]
	else:
	#single data frame
		values = [16*16*16*16*frame[18] + 16*16*frame[17] + frame[16]]
	for k in SVS_PARAMS.keys():
		if SVS_PARAMS[k]["bin"] in frame:
			frame_type = k
			break;
	if "frame_type" in locals():
		print("<- Received %s data (Handle %s):  %s" % (frame_type, hex(handle), hexlify(frame)))
	else:
		print("<- Received unknown data (Handle %s): %s" % (hex(handle), hexlify(frame)))
		return {}
	for val in values:
		if SVS_PARAMS[frame_type]["limits_type"] == "combined":
			sub_frame_type = SVS_PARAMS[frame_type]["limits"][values.index(val)]
		else:
			sub_frame_type = frame_type
		if SVS_PARAMS[sub_frame_type]["limits_type"] == 1:
			check = SVS_PARAMS[sub_frame_type]["limits"]
		else:
			check = range(min(SVS_PARAMS[sub_frame_type]["limits"]),max(SVS_PARAMS[sub_frame_type]["limits"]) + 1)

		if int((val - SVS_PARAMS[sub_frame_type]["reference"])/STEP) in check:
			decoded_values[sub_frame_type] = int((val - SVS_PARAMS[sub_frame_type]["reference"])/STEP)
		elif val == 0 and SVS_PARAMS[sub_frame_type]["reference"] > 0:
			decoded_values[sub_frame_type] = max(check)
		else:
			print("Unrecognized {0} ({1}) values received".format(sub_frame_type, frame_type))
	return decoded_values

class TX:
	BUFFER = ""
	
###################    End SVS Frame Routines    ###################

###################    CRC16 XMODEM Routines    ###################

def checksum_calc(in_data):
	checksum = crcb(*[ int(in_data.hex()[i:i+2], 16) for i in range(0, len(in_data.hex()), 2)])
	checksum = checksum.to_bytes(2, 'little')
	return checksum

def _initial(c):
	crc = 0
	c = c << 8
	for j in range(8):
		if (crc ^ c) & 0x8000:
			crc = (crc << 1) ^ 0x1021
		else:
			crc = crc << 1
		c = c << 1
	return crc

_tab = [ _initial(i) for i in range(256) ]

def _update_crc(crc, c):
	cc = 0xff & c

	tmp = (crc >> 8) ^ cc
	crc = (crc << 8) ^ _tab[tmp & 0xff]
	crc = crc & 0xffff
	return crc

def crcb(*i):
	crc = 0
	for c in i:
		crc = _update_crc(crc, c)
	return crc

###################    End CRC16 XMODEM Routines    ###################

###################    GUI Routines    ###################

def update_vol(self):
	TX.BUFFER = svs_encode("SET","VOLUME",vol_slider.get())

def update_phase(self):
	TX.BUFFER = svs_encode("SET","PHASE", phase_slider.get())

def lfe_opt_changed():
	refresh_widgets()
	TX.BUFFER = svs_encode("SET","LFE",not(lfe_var.get()))

def update_lpfilter_freq(self):
	if not lfe_var.get():
	#as this callback is called when the click is released, be sure only to send svs set only if lfe = off
		TX.BUFFER = svs_encode("SET","LOW_PASS_FILTER_FREQ", lpfilter_slider.get())

def update_lpfilter_slope(self):
	TX.BUFFER = svs_encode("SET","LOW_PASS_FILTER_SLOPE", lpfilter_slope_combo.get().replace(" dB",""))

def room_gain_opt_changed():
	refresh_widgets()
	TX.BUFFER = svs_encode("SET","ROOM_GAIN_ENABLE", room_gain_var.get())

def update_room_gain_freq(self):
	if room_gain_var.get():
	#as this callback is called when the click is released, be sure only to send svs set only if room_gain = on
		TX.BUFFER = svs_encode("SET","ROOM_GAIN_FREQ", room_gain_slider.get())

def update_room_gain_slope(self):
	TX.BUFFER = svs_encode("SET","ROOM_GAIN_SLOPE", room_gain_slope_combo.get().replace(" dB",""))

def make_room_gain__freq_discrete_slider(value):
	new_value = min(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"], key=lambda x:abs(x-float(value)))
	room_gain_slider.set(new_value)

def refresh_widgets(self, values_dict={}):
	for i in values_dict.keys():
		if i == "VOLUME":
			vol_slider.set(values_dict[i])
		elif i == "PHASE":
			phase_slider.set(values_dict[i])
		elif i == "LFE":
			lfe_var.set(not(bool(values_dict[i])))
		elif i == "LOW_PASS_FILTER_FREQ":
			lpfilter_slider.set(values_dict[i])
		elif i == "LOW_PASS_FILTER_SLOPE":
			lpfilter_slope_combo.current(SVS_PARAMS["LOW_PASS_FILTER_SLOPE"]["limits"].index(values_dict[i]))
		elif i == "ROOM_GAIN_ENABLE":
			room_gain_var.set(bool(values_dict[i]))
		elif i == "ROOM_GAIN_FREQ":
			room_gain_slider.set(values_dict[i])
		elif i == "ROOM_GAIN_SLOPE":
			room_gain_slope_combo.current(SVS_PARAMS["ROOM_GAIN_SLOPE"]["limits"].index(values_dict[i]))
		elif i == "POWER_SETTING":
			x = values_dict[i]
	if lfe_var.get() and 'ON' not in lfe_checkbox.cget("text"):
		lpfilter_slider.configure(state='disabled')
		lpfilter_slope_combo.configure(state='disabled')
		lfe_checkbox.configure(text='LFE ON')
	elif not(lfe_var.get()) and 'OFF' not in lfe_checkbox.cget("text"):
		lpfilter_slider.configure(state='normal')
		lpfilter_slope_combo.configure(state='readonly')
		lfe_checkbox.configure(text='LFE OFF')
	if room_gain_var.get() and 'ON' not in room_gain_checkbox.cget("text"):
		room_gain_slider.configure(state='normal')
		room_gain_slope_combo.configure(state='readonly')
		room_gain_checkbox.configure(text='Room Gain Compensation ON')
	elif not(room_gain_var.get()) and 'OFF' not in room_gain_checkbox.cget("text"):
		room_gain_slider.configure(state='disabled')
		room_gain_slope_combo.configure(state='disabled')
		room_gain_checkbox.configure(text='Room Gain Compensation OFF')
	return

def on_closing():
	print("Exiting...")
	global RUN_THREAD
	RUN_THREAD = False
	window.destroy()
	quit()

###################    End GUI Routines    ###################

###################    main()    ###################
VERSION = "v2.6 Beta"
if __name__ == "__main__":
	try:
		window = tk.Tk()
		window.protocol("WM_DELETE_WINDOW", on_closing)
		window.title("pySVS " + VERSION + " - SVS Subwoofer Control")
		window.geometry('550x400')
		window.resizable(False, False)
		style= ttk.Style()
		style.map("TCombobox", fieldbackground=[("readonly", "white"),("disabled", "gray") ])
		window.columnconfigure(16, weight=1)
		window.rowconfigure(16, weight=1)

		vol_slider = tk.Scale(window, from_=min(SVS_PARAMS["VOLUME"]["limits"]), to=max(SVS_PARAMS["VOLUME"]["limits"]), label = "Volume (dB)", orient=tk.HORIZONTAL, resolution=1, length=200)
		vol_slider.grid(column=4, row=3, padx = 20, pady = 15)
		vol_slider.bind("<ButtonRelease-1>", update_vol)

		phase_slider = tk.Scale(window, from_=min(SVS_PARAMS["PHASE"]["limits"]), to=max(SVS_PARAMS["PHASE"]["limits"]), label = "Phase (°)", orient=tk.HORIZONTAL, resolution=1, length=200)
		phase_slider.grid(column=4, row=5, padx = 20, pady = 15)
		phase_slider.bind("<ButtonRelease-1>", update_phase)

		lpfilter_slider = tk.Scale(window, from_=min(SVS_PARAMS["LOW_PASS_FILTER_FREQ"]["limits"]), to=max(SVS_PARAMS["LOW_PASS_FILTER_FREQ"]["limits"]), label = "Low Pass Freq. (Hz)", orient=tk.HORIZONTAL, resolution=1, length=200)
		lpfilter_slider.grid(column=4, row=7, padx = 20, pady = 15)
		lpfilter_slider.bind("<ButtonRelease-1>", update_lpfilter_freq)
		lpfilter_slope_combo=ttk.Combobox(window,values=[str(i) + " dB" for i in SVS_PARAMS["LOW_PASS_FILTER_SLOPE"]["limits"]],width=7,state='readonly')
		lpfilter_slope_combo.grid(column=5, row=7)
		lpfilter_slope_combo.bind("<<ComboboxSelected>>", update_lpfilter_slope)
		lfe_var = tk.BooleanVar(value=False)
		lfe_checkbox = ttk.Checkbutton(variable=lfe_var, command=lfe_opt_changed)
		lfe_checkbox.grid(sticky="W", column=6, row=7)

		room_gain_slider = tk.Scale(window, from_=min(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"]), to=max(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"]), label = "Room Gain Freq. (Hz)", orient=tk.HORIZONTAL, resolution=1, length=200, command=make_room_gain__freq_discrete_slider)
		room_gain_slider.bind("<ButtonRelease-1>", update_room_gain_freq)
		room_gain_slider.grid(column=4, row=9, padx = 20, pady = 15)
		room_gain_slope_combo=ttk.Combobox(window,values=[str(i) + " dB" for i in SVS_PARAMS["ROOM_GAIN_SLOPE"]["limits"]],width=7,state='readonly')
		room_gain_slope_combo.grid(column=5, row=9)
		room_gain_slope_combo.bind("<<ComboboxSelected>>", update_room_gain_slope)
		room_gain_var = tk.BooleanVar(value=True)
		room_gain_checkbox = ttk.Checkbutton(variable=room_gain_var, command=room_gain_opt_changed)
		room_gain_checkbox.grid(sticky="W", column=6, row=9)

		try:
			subwoofer = Image.open(requests.get("https://i.imgur.com/qX85CCG.jpg", stream=True).raw)
			subwoofer = subwoofer.resize((200, 200))
			subwoofer = ImageTk.PhotoImage(subwoofer)
			picframe = tk.Label(window, image = subwoofer)
			picframe.grid(sticky="N", column=5, row=0, columnspan=9, rowspan=9)
		except:
			pass

		threading()
		window.mainloop()

	except Exception:
		traceback.print_exc()

###################    End main()    ###################
