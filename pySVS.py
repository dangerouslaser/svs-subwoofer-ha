#!/usr/bin/python3 

import asyncio
from binascii import crc_hqx, hexlify, unhexlify
from bleak import BleakClient
import getopt
from PIL import ImageTk, Image
import platform
import requests
import sys
from threading import Thread
import time
import tkinter as tk
from tkinter import ttk
import traceback

#EDIT THIS VALUE#####################
SVS_MAC_ADDRESS = "AA:BB:CC:DD:EE:FF"
#####################################

###################    SB-1000-PRO CONFIG    ###################

#SERV01 = "0000fef6-0000-1000-8000-00805f9b34fb"
#CHAR11 = "005f0005-2ff2-4ed5-b045-4c7463617865"
#CHAR12 = "005f0004-2ff2-4ed5-b045-4c7463617865"
#CHAR13 = "005f0003-2ff2-4ed5-b045-4c7463617865"
#CHAR14 = "005f0002-2ff2-4ed5-b045-4c7463617865"

#SERV02 = "1fee6acf-a826-4e37-9635-4d8a01642c5d"
#CHAR21 = "7691b78a-9015-4367-9b95-fc631c412cc6"
CHAR22 = "6409d79d-cd28-479c-a639-92f9e1948b43"

#SERV03 = "0000180a-0000-1000-8000-00805f9b34fb"
#CHAR31 = "00002a29-0000-1000-8000-00805f9b34fb"
#CHAR32 = "00002a25-0000-1000-8000-00805f9b34fb"

#SERV04 = "00001801-0000-1000-8000-00805f9b34fb"
#CHAR41 = "00002a05-0000-1000-8000-00805f9b34fb"

FRAME_PREAMBLE = b'\xaa'

SVS_FRAME_TYPES = {
        "PRESETLOADSAVE": b'\x07\x04',
        "MEMWRITE": b'\xf0\x1f', 
        "MEMREAD": b'\xf1\x1f',
        "READ_RESP": b'\xf2\x00',
        "RESET": b'\xf3\x1f',
        "SUB_INFO1": b'\xf4\x1f',
        "SUB_INFO1_RESP": b'\xf5\x00',
        "SUB_INFO2": b'\xfc\x1f',
        "SUB_INFO2_RESP": b'\xfd\x00',
        "SUB_INFO3": b'\xfe\x1f',
        "SUB_INFO3_RESP": b'\xff\x00'
        }

SVS_PARAMS = {
        "FULL_SETTINGS":{"id":4, "offset":0x0, "limits": [None], "limits_type":"group", "n_bytes":52, "reset_id": -1 }, #group
        "DISPLAY":{"id":4, "offset":0x0, "limits": [0,1,2], "limits_type":1, "n_bytes":2, "reset_id": 0 },  #discrete
        "DISPLAY_TIMEOUT":{"id":4, "offset":0x2,"limits": [0,10,20,30,40,50,60], "limits_type":1, "n_bytes":2, "reset_id": 1 }, #discrete
        "STANDBY":{"id":4, "offset":0x4, "limits": [0,1,2], "limits_type":1, "n_bytes":2, "reset_id": 2 }, #discrete
        "BRIGHTNESS":{"id":4, "offset":0x6, "limits": [0,1,2,3,4,5,6,7], "limits_type":1, "n_bytes":2, "reset_id": 14 }, #discrete
        "LOW_PASS_FILTER_ALL_SETTINGS":{"id":4, "offset":0x8, "limits": [None], "limits_type":"group", "n_bytes":6, "reset_id": 3 }, #group
        "LOW_PASS_FILTER_ENABLE":{"id":4, "offset":0x8, "limits": [0,1], "limits_type":1, "n_bytes":2, "reset_id": 3 }, #discrete
        "LOW_PASS_FILTER_FREQ":{"id":4, "offset":0xa, "limits": [30, 200], "limits_type":0, "n_bytes":2, "reset_id": 3 }, #continous
        "LOW_PASS_FILTER_SLOPE":{"id":4, "offset":0xc,"limits": [6, 12, 18, 24], "limits_type":1, "n_bytes":2, "reset_id": 3 }, #discrete
        "PEQ1_ALL_SETTINGS":{"id":4, "offset":0xe,"limits": [None], "limits_type":"group", "n_bytes":8, "reset_id": 5 }, #group
        "PEQ1_ENABLE":{"id":4, "offset":0xe,"limits": [0,1], "limits_type":1, "n_bytes":2, "reset_id": 5 }, #discrete
        "PEQ1_FREQ":{"id":4, "offset":0x10,"limits": [20,200], "limits_type":0, "n_bytes":2, "reset_id": 5 }, #continous
        "PEQ1_BOOST":{"id":4, "offset":0x12,"limits": [-12.0,6.0], "limits_type":0, "n_bytes":2, "reset_id": 5 }, #continous
        "PEQ1_QFACTOR":{"id":4, "offset":0x14,"limits": [0.2,10.0], "limits_type":0, "n_bytes":2, "reset_id": 5 }, #continous
        "PEQ2_ALL_SETTINGS":{"id":4, "offset":0x16,"limits": [None], "limits_type":"group", "n_bytes":8, "reset_id": 5 }, #group
        "PEQ2_ENABLE":{"id":4, "offset":0x16,"limits": [0,1], "limits_type":1, "n_bytes":2, "reset_id": 5 }, #discrete
        "PEQ2_FREQ":{"id":4, "offset":0x18,"limits": [20,200], "limits_type":0, "n_bytes":2, "reset_id": 5 }, #continous
        "PEQ2_BOOST":{"id":4, "offset":0x1a,"limits": [-12.0,6.0], "limits_type":0, "n_bytes":2, "reset_id": 5 }, #continous
        "PEQ2_QFACTOR":{"id":4, "offset":0x1c,"limits": [0.2,10.0], "limits_type":0, "n_bytes":2, "reset_id": 5 }, #continous
        "PEQ3_ALL_SETTINGS":{"id":4, "offset":0x1e,"limits": [None], "limits_type":"group", "n_bytes":8, "reset_id": 5 }, #group
        "PEQ3_ENABLE":{"id":4, "offset":0x1e,"limits": [0,1], "limits_type":1, "n_bytes":2, "reset_id": 5 }, #discrete
        "PEQ3_FREQ":{"id":4, "offset":0x20,"limits": [20,200], "limits_type":0, "n_bytes":2, "reset_id": 5 }, #continous
        "PEQ3_BOOST":{"id":4, "offset":0x22,"limits": [-12.0,6.0], "limits_type":0, "n_bytes":2, "reset_id": 5 }, #continous
        "PEQ3_QFACTOR":{"id":4, "offset":0x24,"limits": [0.2,10.0], "limits_type":0, "n_bytes":2, "reset_id": 5 }, #continous
        "ROOM_GAIN_ALL_SETTINGS":{"id":4, "offset":0x26, "limits": [None], "limits_type":"group", "n_bytes":6, "reset_id": 8 }, #group
        "ROOM_GAIN_ENABLE":{"id":4, "offset":0x26, "limits": [0,1], "limits_type":1, "n_bytes":2, "reset_id": 8}, #discrete
        "ROOM_GAIN_FREQ":{"id":4, "offset":0x28, "limits": [25, 31, 40], "limits_type":1, "n_bytes":2, "reset_id": 8 }, #discrete
        "ROOM_GAIN_SLOPE":{"id":4, "offset":0x2a, "limits": [6,12], "limits_type":1, "n_bytes":2, "reset_id": 8 }, #discrete
        "VOLUME": {"id":4, "offset":0x2c, "limits": [-60,0], "limits_type":0, "n_bytes":2, "reset_id": 12 }, #continous
        "PHASE": {"id":4, "offset":0x2e, "limits": [0,180], "limits_type":0, "n_bytes":2, "reset_id": 9 }, #continous
        "POLARITY": {"id":4, "offset":0x30, "limits": [0,1], "limits_type":1, "n_bytes":2, "reset_id": 10 }, #discrete
        "PORTTUNING": {"id":4, "offset":0x32, "limits": [20,30], "limits_type":1, "n_bytes":2, "reset_id": 11 }, #discrete
        "PRESET1NAME": {"id":8, "offset":0x0, "limits": [""], "limits_type":2, "n_bytes":8, "reset_id": 13 }, #string
        "PRESET2NAME": {"id":9, "offset":0x0, "limits": [""], "limits_type":2, "n_bytes":8, "reset_id": 13 }, #string
        "PRESET3NAME": {"id":0xA,"offset":0x0, "limits": [""], "limits_type":2, "n_bytes":8, "reset_id": 13 }, #string
        "PRESET1LOAD": {"id":0x18, "offset":0x1, "limits": [None], "limits_type":-1, "n_bytes":0, "reset_id": -1 },
        "PRESET2LOAD": {"id":0x19, "offset":0x1, "limits": [None], "limits_type":-1, "n_bytes":0, "reset_id": -1 },
        "PRESET3LOAD": {"id":0x1A, "offset":0x1, "limits": [None], "limits_type":-1, "n_bytes":0, "reset_id": -1 },
        "PRESET4LOAD": {"id":0x1B, "offset":0x1, "limits": [None], "limits_type":-1, "n_bytes":0, "reset_id": -1 },
        "PRESET1SAVE": {"id":0x1C, "offset":0x1, "limits": [None], "limits_type":-1, "n_bytes":0, "reset_id": -1 },
        "PRESET2SAVE": {"id":0x1D, "offset":0x1, "limits": [None], "limits_type":-1, "n_bytes":0, "reset_id": -1 },
        "PRESET3SAVE": {"id":0x1E, "offset":0x1, "limits": [None], "limits_type":-1, "n_bytes":0, "reset_id": -1 }
        #NOTE: 'group' settings can be read at once but not written at once, the sub doesn't support it.
        }

###################    End SB-1000-PRO CONFIG    ###################

###################    Bleak Routines    ###################

RUN_THREAD = True
PARTIAL_FRAME=b''
sync = True

def RX_thread(handle, data):
    #Everything that the svs subwoofer sends to us comes to this callback
    global PARTIAL_FRAME
    global sync
    if data[0] == int.from_bytes(FRAME_PREAMBLE, 'little'):
    #detected a frame start. Start building frame
        if not sync:
        #sync was not reset before, print error and show PREVIOUS wrong frame
            print("ERROR: Frame fragment out of sync received: %s" % (bytes2hexstr(PARTIAL_FRAME)))
        PARTIAL_FRAME = data
    else:
    #detected a frame fragment. Add it to the previous partial frame
        PARTIAL_FRAME = PARTIAL_FRAME + data

    decoded_frame = svs_decode(PARTIAL_FRAME)
    sync = decoded_frame["FRAME_RECOGNIZED"]
    if sync:
        if GUI:
            print("<- Received %s %s [%s]" % (decoded_frame["FRAME_TYPE"][1], str(decoded_frame["ATTRIBUTES"]), bytes2hexstr(PARTIAL_FRAME)))
            refresh_widgets(decoded_frame["VALIDATED_VALUES"])
        elif not(len(decoded_frame["VALIDATED_VALUES"]) == 1 and "STANDBY" in decoded_frame["ATTRIBUTES"]):
            print(decoded_frame["VALIDATED_VALUES"])

def start_bt_daemon():
    t1=Thread(target=bleak_device)
    t1.start()

def bleak_device():
    ADDRESS = (SVS_MAC_ADDRESS if platform.system() != "Darwin" else "B9EA5233-37EF-4DD6-87A8-2A875E821C46")
    asyncio.run(TX_thread(ADDRESS, CHAR22))

async def TX_thread(address, char_uuid):
    try:
        async with BleakClient(address,adapter=dev) as client:
            if GUI:
                print(f"Connected: {client.is_connected}")
                print("Services:")
                for service in client.services:
                    print(str(service))
                    for char in service.characteristics:
                        print("\t%s" % (str(char)))
                    print("")
            #subscribe to svs parameters characteristic
            await client.start_notify(char_uuid, RX_thread)

            #ask subwoofer for config
            if GUI:
                TX.BUFFER = svs_encode("MEMREAD", "FULL_SETTINGS") + svs_encode("MEMREAD", "PRESET1NAME") + svs_encode("MEMREAD", "PRESET2NAME") + svs_encode("MEMREAD", "PRESET3NAME")

            while RUN_THREAD:
            #don't let this method die in order to RX continuously
                for n in range(0,len(TX.BUFFER), 2):
                    await client.write_gatt_char(char_uuid, TX.BUFFER[0])
                    if GUI:
                        print("-> Sent %s [%s]" % (TX.BUFFER[1], bytes2hexstr(TX.BUFFER[0])))
                    del TX.BUFFER[:2] #remove frame we just sent from buffer and its metadata
                    await asyncio.sleep(0.2)
                await asyncio.sleep(0.2)
    except:
        traceback.print_exc()
        close_bt_daemon()

def close_bt_daemon():
    global RUN_THREAD
    RUN_THREAD = False
    TX.BUFFER = []
    if GUI:
        window.destroy()
        print("Exiting...")
    while True: sys.exit(0)

class TX:
    BUFFER = []
###################    End Bleak Routines    ###################

###################    SVS Frame Routines    ###################

def svs_encode(ftype, param, data=""):
    if ftype == "PRESETLOADSAVE" and SVS_PARAMS[param]["id"] >= 0x18:
    #FRAME FORMAT:
    # PREAMBLE (1 byte) + 
    # 	Frame type (2bytes) + 
    # 		Full frame length (2bytes) +
    # 			ID (4 bytes) +
    # 				Offset to read from/write to (2 bytes) +
    # 					Size to read/write (2 bytes) + 
        frame = SVS_PARAMS[param]["id"].to_bytes(4,"little") + SVS_PARAMS[param]["offset"].to_bytes(2,"little") + SVS_PARAMS[param]["n_bytes"].to_bytes(2,"little")

    elif ftype == "MEMWRITE" and SVS_PARAMS[param]["id"] <= 0xA and SVS_PARAMS[param]["limits_type"] != "group":
    #FRAME FORMAT:
    # PREAMBLE (1 byte) + 
    # 	Frame type (2bytes) + 
    # 		Full frame length (2bytes) +
    # 			ID (4 bytes) +
    # 				Offset to read from/write to (2 bytes) +
    # 					Size to read/write (2 bytes) + 
    # 						Data(0/X bytes) + 
    # 							CRC (2 bytes)
        if type(data) == str and len(data) > 0 and SVS_PARAMS[param]["limits_type"] == 2:
            encoded_data = bytes(data.ljust(SVS_PARAMS[param]["n_bytes"], "\x00"),'utf-8')[:SVS_PARAMS[param]["n_bytes"]]
        elif type(data) in [int, float]:
            if (SVS_PARAMS[param]["limits_type"] == 1 and data in SVS_PARAMS[param]["limits"]) or (SVS_PARAMS[param]["limits_type"] == 0 and max(SVS_PARAMS[param]["limits"]) >= data >= min(SVS_PARAMS[param]["limits"])):
                mask = 0 if data >= 0 else 0xFFFF
                encoded_data = ((int(10 * abs(data)) ^ mask) + (mask % 2)).to_bytes(2, 'little')
            else:
                print("ERROR: Value for %s out of limits" % (param))
                return [b'',""]
        else:
            print("ERROR: Value for %s incorrect" % (param))
            return [b'',""]
        frame = SVS_PARAMS[param]["id"].to_bytes(4,"little") + SVS_PARAMS[param]["offset"].to_bytes(2,"little") + SVS_PARAMS[param]["n_bytes"].to_bytes(2,"little") + encoded_data

    elif ftype == "MEMREAD" and SVS_PARAMS[param]["id"] <= 0xA:
    #FRAME FORMAT:
    # PREAMBLE (1 byte) + 
    # 	Frame type (2bytes) + 
    # 		Full frame length (2bytes) +
    # 			Has Padding (4 bytes) [RESP only] +
    # 				ID (4 bytes) +
    # 					Offset to read from/write to (2 bytes) +
    # 						Size to read/write (2 bytes) + 
    # 							Data(0/X bytes) [RESP only] + 
    # 								PADDING (0/X bytes) [RESP only]
    # 									CRC (2 bytes)
        frame = SVS_PARAMS[param]["id"].to_bytes(4,"little") + SVS_PARAMS[param]["offset"].to_bytes(2,"little") + SVS_PARAMS[param]["n_bytes"].to_bytes(2,"little")

    elif ftype == "RESET" and SVS_PARAMS[param]["id"] <= 0xA:
    #FRAME FORMAT:
    # PREAMBLE (1 byte) + 
    # 	Frame type (2bytes) + 
    # 		Full frame length (2bytes) +
    # 			Reset id (1bytes) +
    # 				CRC (2 bytes)
        frame = SVS_PARAMS[param]["reset_id"].to_bytes(1,"little")

    elif ftype in ["SUB_INFO1", "SUB_INFO2", "SUB_INFO3"]:
    #FRAME FORMAT:
    # PREAMBLE (1 byte) + 
    # 	Frame type (2bytes) + 
    # 		Full frame length (2bytes) +
    # 			Has Padding (4 bytes) [RESP only] +
    #			    b'\x00' +
    # 				    CRC (2 bytes)
        frame = b'\x00'

    else:
        print("ERROR: Unknown frame type to encode. Can only encode DEV-to-SVS frame types.")
        return [b'',""]

    frame = FRAME_PREAMBLE + SVS_FRAME_TYPES[ftype] + (len(frame) + 7).to_bytes(2,"little") + frame
    frame = frame + crc_hqx(frame,0).to_bytes(2, 'little')
    meta = ftype + " " + str([param]) + " "[:len(str(data))] + str(data)
    return [frame, meta]

def svs_decode(frame):
    O_PREAMBLE = frame[0]
    O_ATTRIBUTES = []
    O_FTYPE = "UNKNOWN"
    O_FLENGTH =""
    O_HAS_PADDING = ""
    O_ID = ""
    O_MEM_START = ""
    O_MEM_SIZE = ""
    O_RAW_DATA = b''
    O_B_ENDIAN_DATA = []
    O_VALIDATED_VALUES = {}
    O_RESET_ID = ""
    O_PADDING = ""
    O_CRC = ["0x" + bytes2hexstr(frame[-2:]), "OK" if frame[-2:] == crc_hqx(frame[:-2],0).to_bytes(2, 'little') else "MISSMATCH"]
    O_FLENGTH = ["0x" + bytes2hexstr(frame[3:5]), int.from_bytes(frame[3:5], 'little'), len(frame)]
    O_RECOGNIZED =  (O_PREAMBLE == int.from_bytes(FRAME_PREAMBLE, 'little')) and (O_FLENGTH[1] == O_FLENGTH[2]) and (O_CRC[1] == "OK")
    if O_RECOGNIZED:
        for key in SVS_FRAME_TYPES.keys():
            if SVS_FRAME_TYPES[key] in frame[1:3]:
                O_FTYPE = key
                break;
        O_FTYPE = ["0x" + bytes2hexstr(frame[1:3]), O_FTYPE]
        frame = frame[5:-2] #remove processed bytes from frame
        
        if "RESP" in O_FTYPE[1]:
            O_HAS_PADDING = ["0x" + bytes2hexstr(frame[:4]), frame[:4] == b'\xc4\x00\x00\x20']
            frame = frame [4:] #remove processed bytes from frame

        if O_FTYPE[1] in ["MEMWRITE","MEMREAD","READ_RESP","PRESETLOADSAVE"]:
            O_ID = ["0x" + bytes2hexstr(frame[:4]), int.from_bytes(frame[:4], 'little')]
            mem_start = int.from_bytes(frame[4:6], 'little')
            O_MEM_START = ["0x" + bytes2hexstr(frame[4:6]), mem_start]
            mem_size = int.from_bytes(frame[6:8], 'little')
            O_MEM_SIZE = ["0x" + bytes2hexstr(frame[6:8]), mem_size]
            frame = frame[8:] #remove processed bytes from frame

            #read attributes
            for offset in range(0,mem_size+1,2):
                for key in SVS_PARAMS.keys():
                    if SVS_PARAMS[key]["limits_type"] != "group" and SVS_PARAMS[key]["id"] == O_ID[1]:
                        if (mem_start + offset) == SVS_PARAMS[key]["offset"]:
                            #memory position equal to parameter mem address = PARAMETER MATCH! 
                            O_ATTRIBUTES.append(key)
                            if O_FTYPE[1] in ["READ_RESP", "MEMWRITE"]:
                                #read datas
                                O_B_ENDIAN_DATA.append(int.from_bytes(frame[:SVS_PARAMS[key]["n_bytes"]],'little'))
                                O_RAW_DATA = O_RAW_DATA + frame[:SVS_PARAMS[key]["n_bytes"]]
                                #Validate received values
                                if SVS_PARAMS[key]["limits_type"] == 2:
                                    value = frame[:SVS_PARAMS[key]["n_bytes"]].decode("utf-8").rstrip('\x00')
                                    check = True
                                else:
                                    mask = 0 if O_B_ENDIAN_DATA[-1] < 0xf000 else 0xFFFF
                                    value = ((-1)**(mask % 2)) * ((O_B_ENDIAN_DATA[-1] - (mask % 2)) ^ mask)/10
                                    if SVS_PARAMS[key]["limits_type"] == 1:
                                        check = value in SVS_PARAMS[key]["limits"]
                                    elif SVS_PARAMS[key]["limits_type"] == 0:
                                        check = max(SVS_PARAMS[key]["limits"]) >= value >= min(SVS_PARAMS[key]["limits"]) 
                                if check:
                                    O_VALIDATED_VALUES[key] = int(value) if ".0" in str(value) else value
                                frame = frame[SVS_PARAMS[key]["n_bytes"]:] #remove processed bytes from frame
                            break;
                        elif (mem_start + offset) >= SVS_PARAMS[key]["offset"] and (mem_start + offset) < (SVS_PARAMS[key]["offset"] + SVS_PARAMS[key]["n_bytes"]):
                            #memory position inside a parameter memory range (memory to memory+size) = NO MATCH
                            break;
                        elif (mem_start + offset) < SVS_PARAMS[key]["offset"] or (mem_start + offset) >= (SVS_PARAMS["PORTTUNING"]["offset"] + SVS_PARAMS["PORTTUNING"]["n_bytes"]):
                            #memory position in an undertermined area = NO MATCH
                            O_ATTRIBUTES.append("UNKNOWN")
                            break;

        elif O_FTYPE[1] == "RESET":
            O_RESET_ID = ["0x" + bytes2hexstr(frame), "UNKNOWN"]
            for key in SVS_PARAMS.keys():
                if SVS_PARAMS[key]["reset_id"] == frame[0]:
                    O_RESET_ID[1] = key
                    frame = b''
                    break;

        elif "SUB_INFO" in O_FTYPE[1]:
            if "RESP" in O_FTYPE[1]:
                O_ATTRIBUTES.append(O_FTYPE[1].split("_")[1])
                if "1" in O_FTYPE[1]:
                    control_seq_len = int.from_bytes(frame[:2], 'little')
                    O_VALIDATED_VALUES["DUMP"] = [{"CONTROL_SEQUENCE":bytes2hexstr(frame[2:2+control_seq_len])}, {"ONLY_SOUND_PARAM_DUMP": bytes2hexstr(frame[2+control_seq_len:])}]
                    frame = b''
                elif "2" in O_FTYPE[1]:
                    sw_ver_len = frame[0]
                    O_VALIDATED_VALUES["SW_VERSION"] = frame[1:1+sw_ver_len].decode('utf-8')
                    frame = frame[1+sw_ver_len:]
                elif "3" in O_FTYPE[1]:
                    hw_ver_len = frame[0]
                    O_VALIDATED_VALUES["HW_VERSION"] = frame[1:1+hw_ver_len].decode('utf-8')
                    frame = frame[1+hw_ver_len:]

        #read PADDING
        O_PADDING = "0x" + bytes2hexstr(frame) if(len(frame) > 0) else ""

    output = {}
    for key,val in [("ATTRIBUTES",O_ATTRIBUTES), ("FRAME_RECOGNIZED",O_RECOGNIZED), ("PREAMBLE",str(hex(O_PREAMBLE))), ("FRAME_TYPE",O_FTYPE), ("FRAME_LENGTH", O_FLENGTH), ("HAS PADDING", O_HAS_PADDING), ("ID", O_ID), ("RESET_ID", O_RESET_ID) , ("MEMORY_START", O_MEM_START), ("DATA_LENGTH", O_MEM_SIZE), ("DATA", ["0x" + bytes2hexstr(O_RAW_DATA), O_RAW_DATA, O_B_ENDIAN_DATA] if len(bytes2hexstr(O_RAW_DATA)) > 0 else ""), ("VALIDATED_VALUES", O_VALIDATED_VALUES), ("PADDING", O_PADDING), ("CRC",O_CRC)]:
        if type(val) == bool or len(val) > 0:
            output[key] = val
    return output

def bytes2hexstr(bytes_input):
    return hexlify(bytes_input).decode("utf-8")
    
###################    End SVS Frame Routines    ###################

###################    GUI Routines    ###################

def autoon_combo_changed(self):
    TX.BUFFER += svs_encode("MEMWRITE","STANDBY", autoon_values.index(autoon_combo.get()))

def lpf_opt_changed():
    refresh_widgets()
    TX.BUFFER += svs_encode("MEMWRITE","LOW_PASS_FILTER_ENABLE", int(lpf_var.get()))

def update_lpfilter_freq(self):
    if lpf_var.get():
    #as this callback is called when the click is released, be sure only to send svs memwrite only if lpf = on
        TX.BUFFER += svs_encode("MEMWRITE","LOW_PASS_FILTER_FREQ", lpfilter_slider.get())

def update_lpfilter_slope(self):
    TX.BUFFER += svs_encode("MEMWRITE","LOW_PASS_FILTER_SLOPE", int(lpfilter_slope_combo.get().replace(" dB","")))

def peq1_opt_changed():
    refresh_widgets()
    TX.BUFFER += svs_encode("MEMWRITE","PEQ1_ENABLE", int(PEQ1_var.get()))

def peq2_opt_changed():
    refresh_widgets()
    TX.BUFFER += svs_encode("MEMWRITE","PEQ2_ENABLE", int(PEQ2_var.get()))

def peq3_opt_changed():
    refresh_widgets()
    TX.BUFFER += svs_encode("MEMWRITE","PEQ3_ENABLE", int(PEQ3_var.get()))

def update_peq1_freq(self):
    if PEQ1_var.get():
        TX.BUFFER += svs_encode("MEMWRITE","PEQ1_FREQ", PEQ1_freq_slider.get())

def update_peq1_boost(self):
    if PEQ1_var.get():
        TX.BUFFER += svs_encode("MEMWRITE","PEQ1_BOOST", PEQ1_boost_slider.get())

def update_peq1_qfactor(self):
    if PEQ1_var.get():
        TX.BUFFER += svs_encode("MEMWRITE","PEQ1_QFACTOR", PEQ1_qfactor_slider.get())

def update_peq2_freq(self):
    if PEQ2_var.get():
        TX.BUFFER += svs_encode("MEMWRITE","PEQ2_FREQ", PEQ2_freq_slider.get())

def update_peq2_boost(self):
    if PEQ2_var.get():
        TX.BUFFER += svs_encode("MEMWRITE","PEQ2_BOOST", PEQ2_boost_slider.get())

def update_peq2_qfactor(self):
    if PEQ2_var.get():
        TX.BUFFER += svs_encode("MEMWRITE","PEQ2_QFACTOR", PEQ2_qfactor_slider.get())

def update_peq3_freq(self):
    if PEQ3_var.get():
        TX.BUFFER += svs_encode("MEMWRITE","PEQ3_FREQ", PEQ3_freq_slider.get())

def update_peq3_boost(self):
    if PEQ3_var.get():
        TX.BUFFER += svs_encode("MEMWRITE","PEQ3_BOOST", PEQ3_boost_slider.get())

def update_peq3_qfactor(self):
    if PEQ3_var.get():
        TX.BUFFER += svs_encode("MEMWRITE","PEQ3_QFACTOR", PEQ3_qfactor_slider.get())

def room_gain_opt_changed():
    refresh_widgets()
    TX.BUFFER += svs_encode("MEMWRITE","ROOM_GAIN_ENABLE", int(room_gain_var.get()))

def update_room_gain_freq(event):
    if room_gain_var.get():
    #as this callback is called when the click is released, be sure only to send svs memwrite only if room_gain = on
        current_index = SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"].index(room_gain_slider.get())
        if event.type == "5": #Button1Release
            res = (max(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"]) - min(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"]))/room_gain_slider.cget("length")
            click_release_value = min(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"]) + res * event.x
            if abs(room_gain_slider.get() - click_release_value) > 3: # we were,'t dragging the slider but clicking the scale
                next_index = min(current_index + 1, len(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"]) - 1) if click_release_value > room_gain_slider.get() else max(current_index - 1, 0)
                room_gain_slider.set(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"][next_index])
        elif event.keysym in ['Left', 'Right']: #KeyRelease
            next_index = min(current_index + 1, len(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"]) - 1) if event.keysym == 'Right' else max(current_index - 1, 0)
            room_gain_slider.set(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"][next_index])
        TX.BUFFER += svs_encode("MEMWRITE","ROOM_GAIN_FREQ", room_gain_slider.get())

def update_room_gain_slope(self):
    TX.BUFFER += svs_encode("MEMWRITE","ROOM_GAIN_SLOPE", int(room_gain_slope_combo.get().replace(" dB","")))

def make_room_gain_freq_discrete_slider(value):
    new_value = min(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"], key=lambda x:abs(x-float(value)))
    room_gain_slider.set(new_value)

def update_vol(self):
    TX.BUFFER += svs_encode("MEMWRITE","VOLUME", vol_slider.get())

def update_phase(self):
    TX.BUFFER += svs_encode("MEMWRITE","PHASE", phase_slider.get())

def polarity_opt_changed():
    refresh_widgets()
    TX.BUFFER += svs_encode("MEMWRITE","POLARITY", int(polarity_var.get()))

preset_combo_choice=3
def preset_combo_changed(self):
    global preset_combo_choice
    preset_combo_choice=preset_values.index(preset_combo.get())

def load_preset():
    TX.BUFFER += svs_encode("PRESETLOADSAVE","PRESET" + str(preset_combo_choice + 1) + "LOAD")

def save_preset():
    global preset_combo_choice
    if preset_combo_choice != 3:
    #avoid saving default profile
        TX.BUFFER += svs_encode("PRESETLOADSAVE","PRESET" + str(preset_combo_choice + 1) + "SAVE")

def rename_preset():
    global preset_combo_choice
    if preset_combo_choice != 3:
    #avoid renaming default profile
        filtered_input = string_isalnumify(preset_combo.get())[:SVS_PARAMS["PRESET" + str(preset_combo_choice + 1) + "NAME"]["n_bytes"]]
        if filtered_input not in preset_values and len(filtered_input) > 0:
            preset_combo.set(filtered_input)
            preset_values[preset_combo_choice] = filtered_input
            preset_combo.configure(values=preset_values)
            TX.BUFFER += svs_encode("MEMWRITE","PRESET" + str(preset_combo_choice + 1) + "NAME", filtered_input)
        else:
            preset_combo.set(preset_values[preset_combo_choice])
    else:
        preset_combo.set("DEFAULT")

def refresh_widgets(values_dict={}):
    for key in values_dict.keys():
        if key == "STANDBY":
            autoon_combo.current(int(values_dict[key]))
        elif key == "LOW_PASS_FILTER_ENABLE":
            lpf_var.set(bool(values_dict[key]))
        elif key == "LOW_PASS_FILTER_FREQ":
            lpfilter_slider.configure(state='normal')
            lpfilter_slider.set(values_dict[key])
        elif key == "LOW_PASS_FILTER_SLOPE":
            lpfilter_slope_combo.current(SVS_PARAMS["LOW_PASS_FILTER_SLOPE"]["limits"].index(values_dict[key]))
        elif key == "PEQ1_ENABLE":
            PEQ1_var.set(bool(values_dict[key]))
        elif key == "PEQ1_FREQ":
            PEQ1_freq_slider.configure(state='normal')
            PEQ1_freq_slider.set(values_dict[key])
        elif key == "PEQ1_BOOST":
            PEQ1_boost_slider.configure(state='normal')
            PEQ1_boost_slider.set(values_dict[key])
        elif key == "PEQ1_QFACTOR":
            PEQ1_qfactor_slider.configure(state='normal')
            PEQ1_qfactor_slider.set(values_dict[key])
        elif key == "PEQ2_ENABLE":
            PEQ2_var.set(bool(values_dict[key]))
        elif key == "PEQ2_FREQ":
            PEQ2_freq_slider.configure(state='normal')
            PEQ2_freq_slider.set(values_dict[key])
        elif key == "PEQ2_BOOST":
            PEQ2_boost_slider.configure(state='normal')
            PEQ2_boost_slider.set(values_dict[key])
        elif key == "PEQ2_QFACTOR":
            PEQ2_qfactor_slider.configure(state='normal')
            PEQ2_qfactor_slider.set(values_dict[key])
        elif key == "PEQ3_ENABLE":
            PEQ3_var.set(bool(values_dict[key]))
        elif key == "PEQ3_FREQ":
            PEQ3_freq_slider.configure(state='normal')
            PEQ3_freq_slider.set(values_dict[key])
        elif key == "PEQ3_BOOST":
            PEQ3_boost_slider.configure(state='normal')
            PEQ3_boost_slider.set(values_dict[key])
        elif key == "PEQ3_QFACTOR":
            PEQ3_qfactor_slider.configure(state='normal')
            PEQ3_qfactor_slider.set(values_dict[key])
        elif key == "ROOM_GAIN_ENABLE":
            room_gain_var.set(bool(values_dict[key]))
        elif key == "ROOM_GAIN_FREQ":
            room_gain_slider.configure(state='normal')
            room_gain_slider.set(values_dict[key])
        elif key == "ROOM_GAIN_SLOPE":
            room_gain_slope_combo.current(SVS_PARAMS["ROOM_GAIN_SLOPE"]["limits"].index(values_dict[key]))
        elif key == "VOLUME":
            vol_slider.set(values_dict[key])
        elif key == "PHASE":
            phase_slider.set(values_dict[key])
        elif key == "POLARITY":
            polarity_var.set(bool(values_dict[key]))
        elif "PRESET" in key and "NAME" in key:
            preset_n = int(key.split("PRESET")[1].split("NAME")[0]) - 1
            preset_values[preset_n] = values_dict[key]
            preset_combo.configure(values=preset_values)

    lpfilter_slider.configure(state=['disabled','normal'][int(lpf_var.get())], takefocus=int(lpf_var.get()))
    lpfilter_slope_combo.configure(state=['disabled','readonly'][int(lpf_var.get())])
    lpf_checkbox.configure(text='Low Pass Filter ' + ['OFF (LFE Active)','ON (LFE Inactive)'][int(lpf_var.get())])

    PEQ1_freq_slider.configure(state=['disabled','normal'][int(PEQ1_var.get())], takefocus=int(PEQ1_var.get()))
    PEQ1_boost_slider.configure(state=['disabled','normal'][int(PEQ1_var.get())], takefocus=int(PEQ1_var.get()))
    PEQ1_qfactor_slider.configure(state=['disabled','normal'][int(PEQ1_var.get())], takefocus=int(PEQ1_var.get()))
    PEQ1_checkbox.configure(text='PEQ1 ' + ['Disabled', 'Enabled'][int(PEQ1_var.get())])

    PEQ2_freq_slider.configure(state=['disabled','normal'][int(PEQ2_var.get())], takefocus=int(PEQ2_var.get()))
    PEQ2_boost_slider.configure(state=['disabled','normal'][int(PEQ2_var.get())], takefocus=int(PEQ2_var.get()))
    PEQ2_qfactor_slider.configure(state=['disabled','normal'][int(PEQ2_var.get())], takefocus=int(PEQ2_var.get()))
    PEQ2_checkbox.configure(text='PEQ2 ' + ['Disabled', 'Enabled'][int(PEQ2_var.get())])

    PEQ3_freq_slider.configure(state=['disabled','normal'][int(PEQ3_var.get())], takefocus=int(PEQ3_var.get()))
    PEQ3_boost_slider.configure(state=['disabled','normal'][int(PEQ3_var.get())], takefocus=int(PEQ3_var.get()))
    PEQ3_qfactor_slider.configure(state=['disabled','normal'][int(PEQ3_var.get())], takefocus=int(PEQ3_var.get()))
    PEQ3_checkbox.configure(text='PEQ3 ' + ['Disabled', 'Enabled'][int(PEQ3_var.get())])

    room_gain_slider.configure(state=['disabled','normal'][int(room_gain_var.get())], takefocus=int(room_gain_var.get()))
    room_gain_slope_combo.configure(state=['disabled','readonly'][int(room_gain_var.get())])
    room_gain_checkbox.configure(text='Room Gain Compensation ' + ['OFF', 'ON'][int(room_gain_var.get())])

    polarity_checkbox.configure(text='Polarity ' + ['(+)', '(-)'][int(polarity_var.get())])
    return

def multibinder(widget, function):
    for event in ["<ButtonRelease-1>", "<ButtonRelease-2>", "<KeyRelease-Left>", "<KeyRelease-Right>"]:
        widget.bind(event, function)
    return

###################    End GUI Routines    ###################

###################    main()    ###################

def show_usage():
    print('\npySVS ' + VERSION + '. Read and set SVS SB1000P Subwoofer values. By Logon84 http://github.com/logon84')
    print('Run pySVS.py without arguments to launch the GUI')
    print('USAGE: pySVS.py <-b device> <-m MAC_Address> <parameter1> <value1> <parameter2> <value2> etc...')
    print('\n-b dev or --btiface=dev: Specify a different BT interface to use (default is hci0).')
    print('-m MAC or --mac=MAC: Sets a mac address different to the one set in pySVS.py file.')
    print('-h or --help: Show this help.')
    print('-v or --version: Show program version.')
    print('-e or --encode: Just print built frames based on param values.')
    print('-d FRAME or --decode=FRAME: Decode values of a frame.')
    print('-i or --info: Show subwoofer info.')
    print('-s ftype@param@data or --send ftype@param@data: Send svs_encode frame type, param and data (-s help).')
    print('\nPARAMETER LIST:')
    print('\t-l X@Y@Z or --lpf=X@Y@Z: Sets Low Pass Filter to X[0(OFF),1(ON)], Y[freq] and Z[slope].')
    print('\t-q V@W@X@Y@Z or --peq=V@W@X@Y@Z: Sets PEQ V[1..3], W[0(OFF),1(ON)], X[freq], Y[boost] and Z[Qfactor].')
    print('\t-r X@Y@Z or --roomgain=X@Y@Z: Sets RoomGain X[0(OFF),1(ON)], Y[freq] and Z[slope].')
    print('\t-o X or --volume=X: Sets volume level to X on subwoofer.')
    print('\t-f X or --phase=X: Sets phase level to X on subwoofer.')
    print('\t-k X or --polarity=X: Sets polarity to 0(+) or 1(-) on subwoofer.')
    print('\t-p X or --preset=X: Load preset X[1..4(FACTORY DEFAULT PRESET)] on subwoofer.')
    print('\tTo ask subwoofer for one or more values, set parameter value to \"A\"sk.\n')
    return

def string_isalnumify(in_string):
    return ''.join([char for char in in_string.upper() if char.isalnum()])

if __name__ == "__main__":
    VERSION = "v3.60 Final"
    dev="hci0"
    if len(sys.argv[1:]) > 0:
        GUI = 0
        built_frames = []
        encode=0
        try:
            options, arguments = getopt.getopt(sys.argv[1:],"b:m:hved:is:l:q:r:o:f:k:p:",["btiface=","mac=","help","version","encode","decode=","info", "send=","lpf=","peq=","roomgain=","volume=", "phase=", "polarity=", "preset="])
        except getopt.GetoptError as err:
            show_usage()
            print("ERROR: " + str(err) + "\n")
            sys.exit(2)
        for opt, opt_val in options:
            if opt in ("-m", "--mac"):
                    if len(opt_val.replace("-",":").split(":")) == 6 and len(opt_val) == 17: 
                        SVS_MAC_ADDRESS = opt_val.replace("-",":")
                    else:
                        print("Incorrect MAC specified")
                        sys.exit(1)
            elif opt in ("-h", "--help"):
                show_usage()
                sys.exit(0)
            elif opt in ("-v", "--version"):
                print(VERSION)
                sys.exit(0)
            elif opt in ("-b", "--btiface"):
                dev=opt_val
            elif opt in ("-e", "--encode"):
                encode=1
            elif opt in ("-d", "--decode"):
                print(svs_decode(unhexlify(opt_val.upper().replace("0X",""))))
                sys.exit(0)
            elif opt in ("-i", "--info"):
                built_frames += svs_encode("SUB_INFO1", "") + svs_encode("SUB_INFO2", "") + svs_encode("SUB_INFO3", "")
            elif opt in ("-s", "--send"):
                if opt_val == "help" or len(opt_val.split("@")) !=3:
                    print("FRAME_TYPE@PARAMETER@DATA\n\nAvailable frame types: " + ", ".join(key for key in SVS_FRAME_TYPES.keys() if "RESP" not in key) + "\n\n" + "Available frame parameters: " + ", ".join(key for key in SVS_PARAMS.keys()) + "\n" )
                    sys.exit(0)
                data = opt_val.split("@",2)[2]
                if len(data) > 0:
                    data = string_isalnumify(data) if SVS_PARAMS[opt_val.split("@")[1].upper()]["limits_type"] == 2 else float(data)
                    data = int(data) if type(SVS_PARAMS[opt_val.split("@")[1].upper()]["limits"][0]) == int else data
                built_frames += svs_encode(opt_val.split("@")[0].upper(), opt_val.split("@")[1].upper(), data)
            elif opt in ("-l", "--lpf"):
                if len(opt_val.split("@")) == 3:
                    sub_params = ["LOW_PASS_FILTER_ENABLE","LOW_PASS_FILTER_FREQ","LOW_PASS_FILTER_SLOPE"]
                    for i in range(0,3):
                        if len(opt_val.split("@")[i]) > 0:
                            built_frames += svs_encode("MEMREAD", sub_params[i]) if opt_val.split("@")[i].upper() == 'A' else svs_encode("MEMWRITE", sub_params[i], int(float(opt_val.split("@")[i])))
                else:
                    print("ERROR: Values for LPF incorrect\nExamples of correct values: 1@@12, 0@50@12, A@@6")
                    sys.exit(1)
            elif opt in ("-q", "--peq"):
                if len(opt_val.split("@")) == 5:
                    peq_number = opt_val.split("@")[0]
                    if int(peq_number) in range(1,4):
                        sub_params = ["PEQ" + peq_number + "_ENABLE","PEQ" + peq_number + "_FREQ","PEQ" + peq_number + "_BOOST","PEQ" + peq_number + "_QFACTOR"]
                        for i in range(1,5):
                            if len(opt_val.split("@")[i]) > 0:
                                built_frames += svs_encode("MEMREAD",sub_params[i-1]) if opt_val.split("@")[i].upper() == 'A' else svs_encode("MEMWRITE",sub_params[i-1],float(opt_val.split("@")[i]))
                    else:
                        print("ERROR: PEQ profile number incorrect")
                        sys.exit(1)
                else:
                    print("ERROR: Values for PEQ incorrect\nExamples of correct values: 2@1@@@0.2, 3@0@40@-11.5@10, 1@A@@@")
                    sys.exit(2)
            elif opt in ("-r", "--roomgain"):
                if len(opt_val.split("@")) == 3:
                    sub_params = ["ROOM_GAIN_ENABLE","ROOM_GAIN_FREQ","ROOM_GAIN_SLOPE"]
                    for i in range(0,3):
                        if len(opt_val.split("@")[i]) > 0:
                            built_frames += svs_encode("MEMREAD",sub_params[i]) if opt_val.split("@")[i].upper() == 'A' else svs_encode("MEMWRITE",sub_params[i],int(float(opt_val.split("@")[i])))
                else:
                    print("ERROR: Values for Roomgain incorrect\nExamples of correct values: 1@@12, 0@31@12, A@@6")
                    sys.exit(1)
            elif opt in ("-o", "--volume"):
                built_frames += svs_encode("MEMREAD", "VOLUME") if opt_val.upper() == 'A' else svs_encode("MEMWRITE", "VOLUME", int(float(opt_val)))
            elif opt in ("-f", "--phase"):
                built_frames += svs_encode("MEMREAD", "PHASE") if opt_val.upper() == 'A' else svs_encode("MEMWRITE", "PHASE", int(float(opt_val)))
            elif opt in ("-k", "--polarity"):
                built_frames += svs_encode("MEMREAD", "POLARITY") if opt_val.upper() == 'A' else svs_encode("MEMWRITE", "POLARITY", int(float(opt_val)))
            elif opt in ("-p", "--preset"):
                if int(opt_val) in range (1,5): 
                    built_frames += svs_encode("PRESETLOADSAVE","PRESET" + opt_val + "LOAD")
                else:
                    print("ERROR: Incorrect preset number specified")

        try:
            operands = [int(arg) for arg in arguments]
        except ValueError:
            show_usage()
            sys.exit(2)
            raise SystemExit()

        if len(built_frames) > 0:
            if encode:
                for i in range(0,len(built_frames),2):
                    print(bytes2hexstr(built_frames[i]))
                sys.exit(0)
            else:
                start_bt_daemon()
                TX.BUFFER=built_frames
                while len(TX.BUFFER) > 0: pass
                time.sleep(0.5)
                close_bt_daemon()
        else:
            print("Nothing to do!")
            sys.exit(0)

    else:
        show_usage()
        GUI = 1
        try:
            start_bt_daemon()
            window = tk.Tk()
            window.protocol("WM_DELETE_WINDOW", close_bt_daemon)
            window.title("pySVS " + VERSION + " - SVS Subwoofer Control")
            window.geometry('570x400')
            window.resizable(False, False)
            style= ttk.Style()
            style.theme_use("clam")
            style.map("TCombobox", fieldbackground=[("readonly", "#d2d9d4"),("disabled", "gray") ])
            window.columnconfigure(16, weight=1)
            window.rowconfigure(16, weight=1)
            tabControl = ttk.Notebook(window)
            tabControl.grid(column=0, row=0)
            tab1 = ttk.Frame(tabControl)
            tab2 = ttk.Frame(tabControl)
            tab3 = ttk.Frame(tabControl)
            tabControl.add(tab1, text='General')
            tabControl.add(tab2, text='PEQ')
            tabControl.add(tab3, text='More')
            tabControl.pack(expand = 1, fill ="both")

            vol_slider = tk.Scale(tab1, from_=min(SVS_PARAMS["VOLUME"]["limits"]), to=max(SVS_PARAMS["VOLUME"]["limits"]), label = "Volume (dB)", orient=tk.HORIZONTAL, resolution=10**-int(type(SVS_PARAMS["PHASE"]["limits"][0]) == float), length=200, takefocus=1)
            vol_slider.grid(column=4, row=3, padx = 20, pady = 15)
            multibinder(vol_slider, update_vol)

            phase_slider = tk.Scale(tab1, from_=min(SVS_PARAMS["PHASE"]["limits"]), to=max(SVS_PARAMS["PHASE"]["limits"]), label = "Phase (°)", orient=tk.HORIZONTAL, resolution=10**-int(type(SVS_PARAMS["PHASE"]["limits"][0]) == float), length=200, takefocus=1)
            phase_slider.grid(column=4, row=5, padx = 20, pady = 15)
            multibinder(phase_slider, update_phase)

            lpfilter_slider = tk.Scale(tab1, from_=min(SVS_PARAMS["LOW_PASS_FILTER_FREQ"]["limits"]), to=max(SVS_PARAMS["LOW_PASS_FILTER_FREQ"]["limits"]), label = "Low Pass Filter Freq. (Hz)", orient=tk.HORIZONTAL, resolution=10**-int(type(SVS_PARAMS["LOW_PASS_FILTER_FREQ"]["limits"][0]) == float), length=200, takefocus=1)
            lpfilter_slider.grid(column=4, row=7, padx = 20, pady = 15)
            multibinder(lpfilter_slider, update_lpfilter_freq)
            lpfilter_slope_combo=ttk.Combobox(tab1,values=[str(l) + " dB" for l in SVS_PARAMS["LOW_PASS_FILTER_SLOPE"]["limits"]],width=7,state='readonly')
            lpfilter_slope_combo.grid(sticky="W",column=5, row=7)
            lpfilter_slope_combo.bind("<<ComboboxSelected>>", update_lpfilter_slope)
            lpf_var = tk.BooleanVar(value=False)
            lpf_checkbox = ttk.Checkbutton(tab1, variable=lpf_var, command=lpf_opt_changed)
            lpf_checkbox.place(x=325,y=218)

            room_gain_slider = tk.Scale(tab1, from_=min(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"]), to=max(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"]), label = "Room Gain Freq. (Hz)", orient=tk.HORIZONTAL, resolution=10**-int(type(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"][0]) == float), length=200, takefocus=1, command=make_room_gain_freq_discrete_slider)
            multibinder(room_gain_slider, update_room_gain_freq)
            room_gain_slider.grid(column=4, row=9, padx = 20, pady = 15)
            room_gain_slope_combo=ttk.Combobox(tab1,values=[str(l) + " dB" for l in SVS_PARAMS["ROOM_GAIN_SLOPE"]["limits"]],width=7,state='readonly')
            room_gain_slope_combo.grid(sticky="W",column=5, row=9)
            room_gain_slope_combo.bind("<<ComboboxSelected>>", update_room_gain_slope)
            room_gain_var = tk.BooleanVar(value=True)
            room_gain_checkbox = ttk.Checkbutton(tab1, variable=room_gain_var, command=room_gain_opt_changed)
            room_gain_checkbox.place(x=325,y=310)

            try:
                subwoofer = Image.open(requests.get("https://raw.githubusercontent.com/logon84/pySVS/main/svs1000p.jpg", stream=True).raw)
                subwoofer = subwoofer.resize((200, 200))
                subwoofer = ImageTk.PhotoImage(subwoofer)
                picframe = tk.Label(tab1, image = subwoofer)
                picframe.grid(sticky="NW", column=5, row=0, columnspan=9, rowspan=9, padx=50)
            except:
                pass
            
            PEQ1_var = tk.IntVar(value=0)
            PEQ1_checkbox = ttk.Checkbutton(tab2, variable=PEQ1_var, text='PEQ1', command=peq1_opt_changed)
            PEQ1_checkbox.place(x=40,y=15)
            PEQ1_freq_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ1_FREQ"]["limits"]), to=max(SVS_PARAMS["PEQ1_FREQ"]["limits"]), label = "Freq (Hz)", orient=tk.HORIZONTAL, resolution=10**-int(type(SVS_PARAMS["PEQ1_FREQ"]["limits"][0]) == float), length=100, takefocus=1)
            multibinder(PEQ1_freq_slider, update_peq1_freq)
            PEQ1_freq_slider.grid(column=7, row=3, padx = 35, pady = 35)
            PEQ1_boost_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ1_BOOST"]["limits"]), to=max(SVS_PARAMS["PEQ1_BOOST"]["limits"]), label = "Boost (dB)", orient=tk.HORIZONTAL, resolution=10**-int(type(SVS_PARAMS["PEQ1_BOOST"]["limits"][0]) == float), length=100, takefocus=1)
            multibinder(PEQ1_boost_slider, update_peq1_boost)
            PEQ1_boost_slider.grid(column=7, row=5, padx = 20, pady = 15)
            PEQ1_qfactor_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ1_QFACTOR"]["limits"]), to=max(SVS_PARAMS["PEQ1_QFACTOR"]["limits"]), label = "Q-Factor", orient=tk.HORIZONTAL, resolution=10**-int(type(SVS_PARAMS["PEQ1_QFACTOR"]["limits"][0]) == float), length=100, takefocus=1)
            multibinder(PEQ1_qfactor_slider, update_peq1_qfactor)
            PEQ1_qfactor_slider.grid(column=7, row=7, padx = 20, pady = 35)

            PEQ2_var = tk.IntVar(value=0)
            PEQ2_checkbox = ttk.Checkbutton(tab2, variable=PEQ2_var, text='PEQ2', command=peq2_opt_changed)
            PEQ2_checkbox.place(x=214,y=15)
            PEQ2_freq_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ2_FREQ"]["limits"]), to=max(SVS_PARAMS["PEQ2_FREQ"]["limits"]), label = "Freq (Hz)", orient=tk.HORIZONTAL, resolution=10**-int(type(SVS_PARAMS["PEQ2_FREQ"]["limits"][0]) == float), length=100, takefocus=1)
            multibinder(PEQ2_freq_slider, update_peq2_freq)
            PEQ2_freq_slider.grid(column=8, row=3, padx = 35, pady = 35)
            PEQ2_boost_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ2_BOOST"]["limits"]), to=max(SVS_PARAMS["PEQ2_BOOST"]["limits"]), label = "Boost (dB)", orient=tk.HORIZONTAL, resolution=10**-int(type(SVS_PARAMS["PEQ2_BOOST"]["limits"][0]) == float), length=100, takefocus=1)
            multibinder(PEQ2_boost_slider, update_peq2_boost)
            PEQ2_boost_slider.grid(column=8, row=5, padx = 20, pady = 15)
            PEQ2_qfactor_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ2_QFACTOR"]["limits"]), to=max(SVS_PARAMS["PEQ2_QFACTOR"]["limits"]), label = "Q-Factor", orient=tk.HORIZONTAL, resolution=10**-int(type(SVS_PARAMS["PEQ2_QFACTOR"]["limits"][0]) == float), length=100, takefocus=1)
            multibinder(PEQ2_qfactor_slider, update_peq2_qfactor)
            PEQ2_qfactor_slider.grid(column=8, row=7, padx = 20, pady = 35)

            PEQ3_var = tk.IntVar(value=0)
            PEQ3_checkbox = ttk.Checkbutton(tab2, variable=PEQ3_var, text='PEQ3', command=peq3_opt_changed)
            PEQ3_checkbox.place(x=388,y=15)
            PEQ3_freq_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ3_FREQ"]["limits"]), to=max(SVS_PARAMS["PEQ3_FREQ"]["limits"]), label = "Freq (Hz)", orient=tk.HORIZONTAL, resolution=10**-int(type(SVS_PARAMS["PEQ3_FREQ"]["limits"][0]) == float), length=100, takefocus=1)
            multibinder(PEQ3_freq_slider, update_peq3_freq)
            PEQ3_freq_slider.grid(column=9, row=3, padx = 35, pady = 35)
            PEQ3_boost_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ3_BOOST"]["limits"]), to=max(SVS_PARAMS["PEQ3_BOOST"]["limits"]), label = "Boost (dB)", orient=tk.HORIZONTAL, resolution=10**-int(type(SVS_PARAMS["PEQ3_BOOST"]["limits"][0]) == float), length=100, takefocus=1)
            multibinder(PEQ3_boost_slider, update_peq3_boost)
            PEQ3_boost_slider.grid(column=9, row=5, padx = 20, pady = 15)
            PEQ3_qfactor_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ3_QFACTOR"]["limits"]), to=max(SVS_PARAMS["PEQ3_QFACTOR"]["limits"]), label = "Q-Factor", orient=tk.HORIZONTAL, resolution=10**-int(type(SVS_PARAMS["PEQ3_QFACTOR"]["limits"][0]) == float), length=100, takefocus=1)
            multibinder(PEQ3_qfactor_slider, update_peq3_qfactor)
            PEQ3_qfactor_slider.grid(column=9, row=7, padx = 20, pady = 35)

            preset_label = ttk.Label(tab3, text='Presets:')
            preset_label.grid(column=1, row=1, sticky='W', padx=25, pady=15)
            preset_values = ["MOVIE", "MUSIC", "CUSTOM", "DEFAULT"]
            preset_combo=ttk.Combobox(tab3,values=preset_values,width=7)
            preset_combo.bind("<<ComboboxSelected>>", preset_combo_changed)
            preset_combo.grid(sticky="W",column=1, row=2, padx=30, ipadx = 20)
            preset_combo.current(3)
            preset_rename_button = ttk.Button(tab3, text='Confirm Rename', command=rename_preset)
            preset_rename_button.grid(column=3, row=2)
            preset_load_button = ttk.Button(tab3, text='Load', command=load_preset)
            preset_load_button.grid(column=4, row=2)
            preset_save_button = ttk.Button(tab3, text='Save', command=save_preset)
            preset_save_button.grid(column=5, row=2)
        
            standby_label = ttk.Label(tab3, text='Standby Mode:')
            standby_label.grid(column=1, row=3, sticky='W', padx=25, pady=15)
            autoon_values = ["AUTO ON","TRIGGER","ON"]
            autoon_combo = ttk.Combobox(tab3,values=autoon_values,width=7,state='readonly')
            autoon_combo.bind("<<ComboboxSelected>>", autoon_combo_changed)
            autoon_combo.grid(sticky="W",column=1, row=4, padx=30, ipadx = 20)
            autoon_combo.current(1)

            polarity_var = tk.BooleanVar(value=1)
            polarity_checkbox = ttk.Checkbutton(tab3, variable=polarity_var, command=polarity_opt_changed, text='Polarity')
            polarity_checkbox.place(x=25,y=180)
            
            window.mainloop()

        except Exception:
            traceback.print_exc()

###################    End main()    ###################
