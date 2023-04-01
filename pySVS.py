#!/usr/bin/python3 

from binascii import hexlify
from binascii import unhexlify
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
import getopt


#EDIT THIS VALUE#####################
SVS_MAC_ADDRESS = "01:23:45:67:89:AB"
#####################################

###################    SB-1000-PRO CONFIG    ###################

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

STEP = 10
FRAME_PREAMBLE = b'\xaa'

SVS_FRAME_TYPES = {
        "PRESETLOADSAVE": b'\x07\x04',
        "MEMWRITE": b'\xf0\x1f', 
        "MEMREAD": b'\xf1\x1f',
        "READ_RESP": b'\xf2\x00',
        "RESET": b'\xf3\x1f',
        "SUB_INFO": b'\xf4\x1f',
        "SUB_INFO_RESP": b'\xf5\x00',
        "SUB_INFO2": b'\xfc\x1f',
        "SUB_INFO2_RESP": b'\xfd\x00',
        "SUB_INFO3": b'\xfe\x1f',
        "SUB_INFO3_RESP": b'\xff\x00'
        }

SVS_PARAMS = {
        "FULL_SETTINGS":{"id":4, "offset":0x0, "limits": [], "limits_type":"group", "n_bytes":50, "reset_id": -1 },
        "DISPLAY":{"id":4, "offset":0x0, "limits": [0,1,2], "limits_type":1, "n_bytes":2, "reset_id": -1 },  #discrete
        "DISPLAY_TIMEOUT":{"id":4, "offset":0x2,"limits": [0,10,20,30,40,50,60], "limits_type":1, "n_bytes":2, "reset_id": -1 },  #discrete
        "STANDBY":{"id":4, "offset":0x4, "limits": [0,1,2], "limits_type":1, "n_bytes":2, "reset_id": -1 }, #discrete
        "BRIGHTNESS":{"id":4, "offset":0x6, "limits": [0,1,2,3,4,5,6,7], "limits_type":1, "n_bytes":2, "reset_id": -1 }, #discrete
        "LOW_PASS_FILTER_ALL_SETTINGS":{"id":4, "offset":0x8, "limits": [], "limits_type":"group", "n_bytes":6, "reset_id": 3 }, #group
        "LPF_ENABLE":{"id":4, "offset":0x8, "limits": [0,1], "limits_type":1, "n_bytes":2, "reset_id": 3 }, #discrete
        "LOW_PASS_FILTER_FREQ":{"id":4, "offset":0xa, "limits": [30, 200], "limits_type":0, "n_bytes":2, "reset_id": 3 },
        "LOW_PASS_FILTER_SLOPE":{"id":4, "offset":0xc,"limits": [6, 12, 18, 24], "limits_type":1, "n_bytes":2, "reset_id": 3 }, #discrete
        "PEQ1_ALL_SETTINGS":{"id":4, "offset":0xe,"limits": [], "limits_type":"group", "n_bytes":8, "reset_id": 5 }, #group
        "PEQ1_ENABLE":{"id":4, "offset":0xe,"limits": [0,1], "limits_type":1, "n_bytes":2, "reset_id": 5 }, #discrete
        "PEQ1_FREQ":{"id":4, "offset":0x10,"limits": [20,200], "limits_type":0, "n_bytes":2, "reset_id": 5 },
        "PEQ1_BOOST":{"id":4, "offset":0x12,"limits": [-12.0,6.0], "limits_type":0, "n_bytes":2, "reset_id": 5 },
        "PEQ1_QFACTOR":{"id":4, "offset":0x14,"limits": [0.2,10.0], "limits_type":0, "n_bytes":2, "reset_id": 5 },
        "PEQ2_ALL_SETTINGS":{"id":4, "offset":0x16,"limits": [], "limits_type":"group", "n_bytes":8, "reset_id": 5 }, #group
        "PEQ2_ENABLE":{"id":4, "offset":0x16,"limits": [0,1], "limits_type":1, "n_bytes":2, "reset_id": 5 }, #discrete
        "PEQ2_FREQ":{"id":4, "offset":0x18,"limits": [20,200], "limits_type":0, "n_bytes":2, "reset_id": 5 },
        "PEQ2_BOOST":{"id":4, "offset":0x1a,"limits": [-12.0,6.0], "limits_type":0, "n_bytes":2, "reset_id": 5 },
        "PEQ2_QFACTOR":{"id":4, "offset":0x1c,"limits": [0.2,10.0], "limits_type":0, "n_bytes":2, "reset_id": 5 },
        "PEQ3_ALL_SETTINGS":{"id":4, "offset":0x1e,"limits": [], "limits_type":"group", "n_bytes":8, "reset_id": 5 }, #group
        "PEQ3_ENABLE":{"id":4, "offset":0x1e,"limits": [0,1], "limits_type":1, "n_bytes":2, "reset_id": 5 }, #discrete
        "PEQ3_FREQ":{"id":4, "offset":0x20,"limits": [20,200], "limits_type":0, "n_bytes":2, "reset_id": 5 },
        "PEQ3_BOOST":{"id":4, "offset":0x22,"limits": [-12.0,6.0], "limits_type":0, "n_bytes":2, "reset_id": 5 },
        "PEQ3_QFACTOR":{"id":4, "offset":0x24,"limits": [0.2,10.0], "limits_type":0, "n_bytes":2, "reset_id": 5 },
        "ROOM_GAIN_ALL_SETTINGS":{"id":4, "offset":0x26, "limits": [], "limits_type":"group", "n_bytes":6, "reset_id": 8 }, #group
        "ROOM_GAIN_ENABLE":{"id":4, "offset":0x26, "limits": [0,1], "limits_type":1, "n_bytes":2, "reset_id": 8}, #discrete
        "ROOM_GAIN_FREQ":{"id":4, "offset":0x28, "limits": [25, 31, 40], "limits_type":1, "n_bytes":2, "reset_id": 8 }, #discrete
        "ROOM_GAIN_SLOPE":{"id":4, "offset":0x2a, "limits": [6,12], "limits_type":1, "n_bytes":2, "reset_id": 8 }, #discrete
        "VOLUME": {"id":4, "offset":0x2c, "limits": [-60,0], "limits_type":0, "n_bytes":2, "reset_id": 12 },
        "PHASE": {"id":4, "offset":0x2e, "limits": [0,180], "limits_type":0, "n_bytes":2, "reset_id": 9 },
        "POLARITY": {"id":4, "offset":0x30, "limits": [0,1], "limits_type":1, "n_bytes":2, "reset_id": 10 }, #discrete
        "PORTTUNING": {"id":4, "offset":0x32, "limits": [0, 1, 2], "limits_type":1, "n_bytes":2, "reset_id": -1 }, #discrete
        "PRESET1NAME": {"id":8, "offset":0x0, "limits": [], "limits_type":2, "n_bytes":8, "reset_id": 13 }, #string
        "PRESET2NAME": {"id":9, "offset":0x0, "limits": [], "limits_type":2, "n_bytes":8, "reset_id": 13 }, #string
        "PRESET3NAME": {"id":0xA,"offset":0x0, "limits": [], "limits_type":2, "n_bytes":8, "reset_id": 13 }, #string
        "PRESET1LOAD": {"id":0x18, "offset":0x1, "limits": [], "limits_type":1, "n_bytes":0, "reset_id": -1 },
        "PRESET2LOAD": {"id":0x19, "offset":0x1, "limits": [], "limits_type":1, "n_bytes":0, "reset_id": -1 },
        "PRESET3LOAD": {"id":0x1A, "offset":0x1, "limits": [], "limits_type":1, "n_bytes":0, "reset_id": -1 },
        "PRESET4LOAD": {"id":0x1B, "offset":0x1, "limits": [], "limits_type":1, "n_bytes":0, "reset_id": -1},
        "PRESET1SAVE": {"id":0x1C, "offset":0x1, "limits": [0,1], "limits_type":1, "n_bytes":0, "reset_id": -1 },
        "PRESET2SAVE": {"id":0x1D, "offset":0x1, "limits": [0,1], "limits_type":1, "n_bytes":0, "reset_id": -1 },
        "PRESET3SAVE": {"id":0x1E, "offset":0x1, "limits": [0,1], "limits_type":1, "n_bytes":0, "reset_id": -1 }
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
    if decoded_frame["FRAME_RECOGNIZED"]:
        if GUI:
            print("<- Received %s %s [%s]" % (decoded_frame["FRAME_TYPE"][1], str(decoded_frame["ATTRIBUTES"]).replace("\'","").replace("]","").replace("[","").replace(", ","+"), bytes2hexstr(PARTIAL_FRAME)))
            refresh_widgets(decoded_frame["VALIDATED_VALUES"])
        elif "STANDBY" not in decoded_frame["ATTRIBUTES"]:
            print(decoded_frame["VALIDATED_VALUES"])
    sync = decoded_frame["FRAME_RECOGNIZED"]

def threading():
    # Call function
    t1=Thread(target=bleak_device)
    t1.start()

def bleak_device():
    ADDRESS = (SVS_MAC_ADDRESS if platform.system() != "Darwin" else "B9EA5233-37EF-4DD6-87A8-2A875E821C46")
    asyncio.run(TX_thread(ADDRESS, CHAR12))

async def TX_thread(address, char_uuid):
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
                del TX.BUFFER[0:2] #remove frame we just sent from buffer and its metadata
                await asyncio.sleep(0.2)
            await asyncio.sleep(0.2)

class TX:
    BUFFER = []
###################    End Bleak Routines    ###################

###################    SVS Frame Routines    ###################

def svs_encode(ftype, param, data=[]):
    encoded_data = b''
    frame = FRAME_PREAMBLE + SVS_FRAME_TYPES[ftype]
    if ftype == "PRESETLOADSAVE":
	#FRAME FORMAT:
    # PREAMBLE (1 byte) + 
    # 	Frame type (2bytes) + 
    # 		Full frame length (2bytes) +
    # 			ID (4 bytes) +
    # 				Offset to read from/write to (2 bytes) +
    # 					Size to read/write (2 bytes) + 
        frame = frame + SVS_PARAMS[param]["id"].to_bytes(4,"little") + SVS_PARAMS[param]["offset"].to_bytes(2,"little") + SVS_PARAMS[param]["n_bytes"].to_bytes(2,"little")
    elif ftype == "MEMWRITE":
	#FRAME FORMAT:
    # PREAMBLE (1 byte) + 
    # 	Frame type (2bytes) + 
    # 		Full frame length (2bytes) +
    # 			ID (4 bytes) +
    # 				Offset to read from/write to (2 bytes) +
    # 					Size to read/write (2 bytes) + 
    # 						Data(0/X bytes) + 
    # 							CRC (2 bytes)
        if type(data[0]) == str:
            encoded_data = bytes(data.ljust(int(SVS_PARAMS[param]["n_bytes"]), "\x00"),'utf-8')[:SVS_PARAMS[param]["n_bytes"]]
        else:
            if len(data) == SVS_PARAMS[param]["n_bytes"]/2:
                for val in data:
                    mask = 0 if val >= 0 else 0xFFFF
                    encoded_data = encoded_data + ((int(STEP * abs(val)) ^ mask) + (mask % 2)).to_bytes(2, 'little')
            else:
                print("ERROR: %s requires %s values and %s were given" % (param, str(int(SVS_PARAMS[param]["n_bytes"]/2)), str(len(data))))
                on_closing()
        frame = frame + SVS_PARAMS[param]["id"].to_bytes(4,"little") + SVS_PARAMS[param]["offset"].to_bytes(2,"little") + SVS_PARAMS[param]["n_bytes"].to_bytes(2,"little") + encoded_data
    elif ftype == "MEMREAD":
	#FRAME FORMAT:
    # PREAMBLE (1 byte) + 
    # 	Frame type (2bytes) + 
    # 		Full frame length (2bytes) +
    # 			SECT_1 (0/4 bytes) [RESP only] +
    # 				ID (4 bytes) +
    # 					Offset to read from/write to (2 bytes) +
    # 						Size to read/write (2 bytes) + 
    # 							Data(0/X bytes) [RESP only] + 
    # 								PADDING (0/X bytes) [RESP only]
    # 									CRC (2 bytes)
        frame = frame + SVS_PARAMS[param]["id"].to_bytes(4,"little") + SVS_PARAMS[param]["offset"].to_bytes(2,"little") + SVS_PARAMS[param]["n_bytes"].to_bytes(2,"little")
    elif ftype == "RESET":
	#FRAME FORMAT:
    # PREAMBLE (1 byte) + 
    # 	Frame type (2bytes) + 
    # 		Full frame length (2bytes) +
    # 			Reset id (1bytes) +
    # 				CRC (2 bytes)
        frame = frame + SVS_PARAMS[param]["reset_id"].to_bytes(1,"little")
    elif "SUB_INFO" in ftype and "RESP" not in ftype:
	#FRAME FORMAT:
    # PREAMBLE (1 byte) + 
    # 	Frame type (2bytes) + 
    # 		Full frame length (2bytes) +
	#			b'\x00' +
    # 				CRC (2 bytes)
        frame = frame + b'\x00'
    else:
        print("ERROR: Can only encode DEV-to-SVS frame types")
        on_closing()
    frame = frame[:3] + (len(frame) + 4).to_bytes(2,"little") + frame[3:]
    frame = frame + checksum_calc(frame)
    meta = ftype + " " + param + " " + str(data) if len(data)>0 else ftype + " " + param
    return [frame, meta]

def svs_decode(frame):
    O_ATTRIBUTES = []
    O_FTYPE = "UNKNOWN"
    O_FLENGTH =""
    O_SECT_1 = ""
    O_ID = ""
    O_MEM_START = ""
    O_MEM_SIZE = ""
    O_RAW_DATA = b''
    O_B_ENDIAN_DATA = []
    O_VALIDATED_VALUES = {}
    O_PADDING = ""

    O_CRC = ["0x" + bytes2hexstr(frame[len(frame) - 2:]), "OK" if frame[len(frame)-2:] == checksum_calc(frame[:len(frame)-2]) else "MISSMATCH"]
    O_FLENGTH = ["0x" + bytes2hexstr(frame[3:5]), int.from_bytes(frame[3:5], 'little'), len(frame)]
    O_RECOGNIZED =  (frame[0] == int.from_bytes(FRAME_PREAMBLE, 'little')) and (O_FLENGTH[1] == O_FLENGTH[2]) and (O_CRC[1] == "OK")
    if O_RECOGNIZED:
        for key in SVS_FRAME_TYPES.keys():
            if SVS_FRAME_TYPES[key] in frame[1:3]:
                O_FTYPE = key
                break;
        O_FTYPE = ["0x" + bytes2hexstr(frame[1:3]), O_FTYPE]
        if O_FTYPE[1] == "PRESETLOADSAVE":
            ID_position = 5
            O_ID = ["0x" + bytes2hexstr(frame[ID_position:ID_position + 4]), int.from_bytes(frame[ID_position:ID_position + 4], 'little')]
            for key in SVS_PARAMS.keys():
                if SVS_PARAMS[key]["id"] == O_ID[1]:
                    O_ID =  O_ID + [key]
                    break;
            mem_start = int.from_bytes(frame[ID_position + 4:ID_position + 6], 'little')
            O_MEM_START = "0x" + bytes2hexstr(frame[ID_position + 4:ID_position + 6])
            mem_size = int.from_bytes(frame[6+ID_position:8+ID_position], 'little')
            O_MEM_SIZE = ["0x" + bytes2hexstr(frame[6 + ID_position:8 + ID_position]), mem_size]
            output = {"ATTRIBUTES": O_ATTRIBUTES, "FRAME_RECOGNIZED": O_RECOGNIZED, "PREAMBLE": str(hex(frame[0])), "FRAME_TYPE": O_FTYPE, "FRAME_LENGTH": O_FLENGTH, "ID": O_ID, "MEMORY_START": O_MEM_START, "DATA_LENGTH": O_MEM_SIZE, "CRC":O_CRC}

        elif O_FTYPE[1] in ["MEMWRITE","MEMREAD","READ_RESP"]:
            ID_position = 9 if O_FTYPE[1] == "READ_RESP" else 5
            O_SECT_1 = "0x" + bytes2hexstr(frame[5:ID_position]) if ID_position > 5 else ""
            O_ID = ["0x" + bytes2hexstr(frame[ID_position:ID_position + 4]), int.from_bytes(frame[ID_position:ID_position + 4], 'little')]
            mem_start = int.from_bytes(frame[ID_position + 4:ID_position + 6], 'little')
            O_MEM_START = "0x" + bytes2hexstr(frame[ID_position + 4:ID_position + 6])
            mem_size = int.from_bytes(frame[6+ID_position:8+ID_position], 'little')
            O_MEM_SIZE = ["0x" + bytes2hexstr(frame[6 + ID_position:8 + ID_position]), mem_size]
            bytes_left_in_frame = len(frame[8 + ID_position:])

            #read attributes
            for offset in range(0,int(mem_size),2):
                for key in SVS_PARAMS.keys():
                    if SVS_PARAMS[key]["limits_type"] != "group" and SVS_PARAMS[key]["id"] == O_ID[1]:
                        if (mem_start + offset) == SVS_PARAMS[key]["offset"]:
                        #memory position equal to parameter mem address
                            O_ATTRIBUTES.append(key)
                            break;
                        elif (mem_start + offset) >= SVS_PARAMS[key]["offset"] and (mem_start + offset) < (SVS_PARAMS[key]["offset"] + SVS_PARAMS[key]["n_bytes"]):
                        #memory position inside a parameter memory range (memory to memory+size)
                            break;
                        elif (mem_start + offset) < SVS_PARAMS[key]["offset"] or (mem_start + offset) >= (SVS_PARAMS["PORTTUNING"]["offset"] + SVS_PARAMS["PORTTUNING"]["n_bytes"]):
                        #memory position in an undertermined area
                            O_ATTRIBUTES.append("UNKNOWN")
                            break;

            #read datas
            if bytes_left_in_frame - 2 >= mem_size:
                for attrib in O_ATTRIBUTES:
                    for offset in range(len(O_B_ENDIAN_DATA),int(SVS_PARAMS[attrib]["n_bytes"]/2) + len(O_B_ENDIAN_DATA)):
                        O_B_ENDIAN_DATA.append(int.from_bytes(frame[ID_position + 8 + 2*offset:ID_position + 10 + 2*offset],'little'))
                        O_RAW_DATA = O_RAW_DATA + frame[ID_position + 8 + 2*offset:ID_position + 10 + 2*offset]
                        bytes_left_in_frame = bytes_left_in_frame - 2
                        if attrib != "UNKNOWN":
                           #Validate received values
                            if SVS_PARAMS[attrib]["limits_type"] == 2:
                                value = str(O_RAW_DATA)[2:len(str(O_RAW_DATA))-1].rstrip(str(b'\x00'))
                                check = True
                            else:
                                mask = 0 if O_B_ENDIAN_DATA[offset] < 0xf000 else 0xFFFF
                                value = ((-1)**(mask % 2)) * ((O_B_ENDIAN_DATA[offset] - (mask % 2)) ^ mask)/STEP
                                if SVS_PARAMS[attrib]["limits_type"] == 1:
                                    check = value in SVS_PARAMS[attrib]["limits"]
                                elif SVS_PARAMS[attrib]["limits_type"] == 0:
                                    check = max(SVS_PARAMS[attrib]["limits"]) >= value >= min(SVS_PARAMS[attrib]["limits"]) 

                            if check:
                                O_VALIDATED_VALUES[attrib] = value

            #read PADDING
            O_PADDING = "0x" + bytes2hexstr(frame[len(frame) - bytes_left_in_frame:len(frame)-2]) if(len(bytes2hexstr(frame[len(frame) - bytes_left_in_frame:len(frame)-2])) > 0) else ""
            output = {"ATTRIBUTES": O_ATTRIBUTES, "FRAME_RECOGNIZED": O_RECOGNIZED, "PREAMBLE": str(hex(frame[0])), "FRAME_TYPE": O_FTYPE, "FRAME_LENGTH": O_FLENGTH, "SECT_1": O_SECT_1, "ID": O_ID, "MEMORY_START": O_MEM_START, "DATA_LENGTH": O_MEM_SIZE, "RAW_DATA": "0x" + bytes2hexstr(O_RAW_DATA), "INT_DATA": O_B_ENDIAN_DATA, "STR_DATA": O_RAW_DATA, "VALIDATED_VALUES": O_VALIDATED_VALUES, "PADDING": O_PADDING, "CRC":O_CRC}
        if O_FTYPE[1] == "RESET":
            O_RESET_ID = ["0x" + bytes2hexstr(frame[5:6]), "UNKNOWN"]
            for key in SVS_PARAMS.keys():
                if SVS_PARAMS[key]["reset_id"] == frame[5]:
                    O_RESET_ID[1] = key
                    break;
            output = {"FRAME_RECOGNIZED": O_RECOGNIZED, "PREAMBLE": str(hex(frame[0])), "FRAME_TYPE": O_FTYPE, "FRAME_LENGTH": O_FLENGTH, "RESET_ID": O_RESET_ID, "CRC":O_CRC}
        if "SUB_INFO" in O_FTYPE[1] and "RESP" in O_FTYPE[1]:
            internal_data_length = int(len(bytes2hexstr(frame[5: len(frame) - 2]).rstrip(str(b'\x00')))/2)
            O_STR_DATA = frame[5:5 + internal_data_length]
            O_PADDING = "0x" + bytes2hexstr(frame[6 + internal_data_length:len(frame) - 2])
            output = {"ATTRIBUTES": O_ATTRIBUTES,"FRAME_RECOGNIZED": O_RECOGNIZED, "PREAMBLE": str(hex(frame[0])), "FRAME_TYPE": O_FTYPE, "FRAME_LENGTH": O_FLENGTH, "STR_DATA": O_STR_DATA, "VALIDATED_VALUES": O_VALIDATED_VALUES, "PADDING": O_PADDING, "CRC":O_CRC}
        else:
            output = {"ATTRIBUTES": O_ATTRIBUTES, "FRAME_RECOGNIZED": O_RECOGNIZED, "PREAMBLE": str(hex(frame[0])), "FRAME_TYPE": O_FTYPE, "FRAME_LENGTH": O_FLENGTH, "VALIDATED_VALUES": O_VALIDATED_VALUES, "PADDING": O_PADDING, "CRC":O_CRC}
    else:
        output = {"FRAME_RECOGNIZED": O_RECOGNIZED, "PREAMBLE": str(hex(frame[0])), "FRAME_TYPE": O_FTYPE, "FRAME_LENGTH": O_FLENGTH, "CRC":O_CRC}
    return output

def bytes2hexstr(bytes_input):
    return str(hexlify(bytes_input)).replace("\'","")[1:]
    
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

def autoon_combo_changed(self):
    TX.BUFFER = svs_encode("MEMWRITE","STANDBY", [autoon_values.index(autoon_combo.get())])

def lpf_opt_changed():
    refresh_widgets()
    TX.BUFFER = svs_encode("MEMWRITE","LPF_ENABLE",[int(lpf_var.get())])

def update_lpfilter_freq(self):
    if lpf_var.get():
    #as this callback is called when the click is released, be sure only to send svs memwrite only if lpf = on
        TX.BUFFER = svs_encode("MEMWRITE","LOW_PASS_FILTER_FREQ", [lpfilter_slider.get()])

def update_lpfilter_slope(self):
    TX.BUFFER = svs_encode("MEMWRITE","LOW_PASS_FILTER_SLOPE", [int(lpfilter_slope_combo.get().replace(" dB",""))])

def peq1_opt_changed():
    refresh_widgets()
    TX.BUFFER = svs_encode("MEMWRITE","PEQ1_ENABLE",[int(PEQ1_var.get())])

def peq2_opt_changed():
    refresh_widgets()
    TX.BUFFER = svs_encode("MEMWRITE","PEQ2_ENABLE",[int(PEQ2_var.get())])

def peq3_opt_changed():
    refresh_widgets()
    TX.BUFFER = svs_encode("MEMWRITE","PEQ3_ENABLE",[int(PEQ3_var.get())])

def update_peq1_freq(self):
    if PEQ1_var.get():
        TX.BUFFER = svs_encode("MEMWRITE","PEQ1_FREQ", [PEQ1_freq_slider.get()])

def update_peq1_boost(self):
    if PEQ1_var.get():
        TX.BUFFER = svs_encode("MEMWRITE","PEQ1_BOOST", [PEQ1_boost_slider.get()])

def update_peq1_qfactor(self):
    if PEQ1_var.get():
        TX.BUFFER = svs_encode("MEMWRITE","PEQ1_QFACTOR", [PEQ1_qfactor_slider.get()])

def update_peq2_freq(self):
    if PEQ2_var.get():
        TX.BUFFER = svs_encode("MEMWRITE","PEQ2_FREQ", [PEQ2_freq_slider.get()])

def update_peq2_boost(self):
    if PEQ2_var.get():
        TX.BUFFER = svs_encode("MEMWRITE","PEQ2_BOOST", [PEQ2_boost_slider.get()])

def update_peq2_qfactor(self):
    if PEQ2_var.get():
        TX.BUFFER = svs_encode("MEMWRITE","PEQ2_QFACTOR", [PEQ2_qfactor_slider.get()])

def update_peq3_freq(self):
    if PEQ3_var.get():
        TX.BUFFER = svs_encode("MEMWRITE","PEQ3_FREQ", [PEQ3_freq_slider.get()])

def update_peq3_boost(self):
    if PEQ3_var.get():
        TX.BUFFER = svs_encode("MEMWRITE","PEQ3_BOOST", [PEQ3_boost_slider.get()])

def update_peq3_qfactor(self):
    if PEQ3_var.get():
        TX.BUFFER = svs_encode("MEMWRITE","PEQ3_QFACTOR", [PEQ3_qfactor_slider.get()])

def room_gain_opt_changed():
    refresh_widgets()
    TX.BUFFER = svs_encode("MEMWRITE","ROOM_GAIN_ENABLE", [int(room_gain_var.get())])

def update_room_gain_freq(self):
    if room_gain_var.get():
    #as this callback is called when the click is released, be sure only to send svs memwrite only if room_gain = on
        TX.BUFFER = svs_encode("MEMWRITE","ROOM_GAIN_FREQ", [room_gain_slider.get()])

def update_room_gain_slope(self):
    TX.BUFFER = svs_encode("MEMWRITE","ROOM_GAIN_SLOPE", [int(room_gain_slope_combo.get().replace(" dB",""))])

def make_room_gain__freq_discrete_slider(value):
    new_value = min(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"], key=lambda x:abs(x-float(value)))
    room_gain_slider.set(new_value)

def update_vol(self):
    TX.BUFFER = svs_encode("MEMWRITE","VOLUME",[vol_slider.get()])

def update_phase(self):
    TX.BUFFER = svs_encode("MEMWRITE","PHASE", [phase_slider.get()])

def polarity_opt_changed():
    refresh_widgets()
    TX.BUFFER = svs_encode("MEMWRITE","POLARITY",[int(polarity_var.get())])

preset_combo_choice=3
def preset_combo_changed(self):
    global preset_combo_choice
    preset_combo_choice=preset_values.index(preset_combo.get())

def load_preset():
    TX.BUFFER = svs_encode("PRESETLOADSAVE","PRESET" + str(preset_combo_choice + 1) + "LOAD")

def save_preset():
    global preset_combo_choice
    if preset_combo_choice != 3:
    #avoid saving default profile
        TX.BUFFER = svs_encode("PRESETLOADSAVE","PRESET" + str(preset_combo_choice + 1) + "SAVE")

def rename_preset():
    global preset_combo_choice
    if preset_combo_choice != 3:
    #avoid renaming default profile
        filtered_input = ''.join([char for char in preset_combo.get().upper() if char.isalnum()])
        filtered_input = filtered_input[:8]
        if filtered_input not in preset_values:
            preset_combo.set(filtered_input)
            preset_values[preset_combo_choice] = filtered_input
            preset_combo.configure(values=preset_values)
            TX.BUFFER = svs_encode("MEMWRITE","PRESET" + str(preset_combo_choice + 1) + "NAME", filtered_input)
        else:
            preset_combo.set(preset_values[preset_combo_choice])
    else:
        preset_combo.set("DEFAULT")

def refresh_widgets(values_dict={}):
    for key in values_dict.keys():
        if key == "STANDBY":
            autoon_combo.current(int(values_dict[key]))
        elif key == "LPF_ENABLE":
            lpf_var.set(bool(values_dict[key]))
        elif key == "LOW_PASS_FILTER_FREQ":
            lpfilter_slider.set(values_dict[key])
        elif key == "LOW_PASS_FILTER_SLOPE":
            lpfilter_slope_combo.current(SVS_PARAMS["LOW_PASS_FILTER_SLOPE"]["limits"].index(values_dict[key]))
        elif key == "PEQ1_ENABLE":
            PEQ1_var.set(bool(values_dict[key]))
        elif key == "PEQ1_FREQ":
            PEQ1_freq_slider.set(values_dict[key])
        elif key == "PEQ1_BOOST":
            PEQ1_boost_slider.set(values_dict[key])
        elif key == "PEQ1_QFACTOR":
            PEQ1_qfactor_slider.set(values_dict[key])
        elif key == "PEQ2_ENABLE":
            PEQ2_var.set(bool(values_dict[key]))
        elif key == "PEQ2_FREQ":
            PEQ2_freq_slider.set(values_dict[key])
        elif key == "PEQ2_BOOST":
            PEQ2_boost_slider.set(values_dict[key])
        elif key == "PEQ2_QFACTOR":
            PEQ2_qfactor_slider.set(values_dict[key])
        elif key == "PEQ3_ENABLE":
            PEQ3_var.set(bool(values_dict[key]))
        elif key == "PEQ3_FREQ":
            PEQ3_freq_slider.set(values_dict[key])
        elif key == "PEQ3_BOOST":
            PEQ3_boost_slider.set(values_dict[key])
        elif key == "PEQ3_QFACTOR":
            PEQ3_qfactor_slider.set(values_dict[key])
        elif key == "ROOM_GAIN_ENABLE":
            room_gain_var.set(bool(values_dict[key]))
        elif key == "ROOM_GAIN_FREQ":
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
    if lpf_var.get() and 'ON' not in lpf_checkbox.cget("text"):
        lpfilter_slider.configure(state='normal')
        lpfilter_slope_combo.configure(state='readonly')
        lpf_checkbox.configure(text='Low Pass Filter ON (LFE Inactive)')
    elif not(lpf_var.get()) and 'OFF' not in lpf_checkbox.cget("text"):
        lpfilter_slider.configure(state='disabled')
        lpfilter_slope_combo.configure(state='disabled')
        lpf_checkbox.configure(text='Low Pass Filter OFF (LFE Active)')
    if PEQ1_var.get() and 'Enabled' not in PEQ1_checkbox.cget("text"):
        PEQ1_freq_slider.configure(state='normal')
        PEQ1_boost_slider.configure(state='normal')
        PEQ1_qfactor_slider.configure(state='normal')
        PEQ1_checkbox.configure(text='PEQ1 Enabled')
    elif not(PEQ1_var.get()) and 'Disabled' not in PEQ1_checkbox.cget("text"):
        PEQ1_freq_slider.configure(state='disabled')
        PEQ1_boost_slider.configure(state='disabled')
        PEQ1_qfactor_slider.configure(state='disabled')
        PEQ1_checkbox.configure(text='PEQ1 Disabled')
    if PEQ2_var.get() and 'Enabled' not in PEQ2_checkbox.cget("text"):
        PEQ2_freq_slider.configure(state='normal')
        PEQ2_boost_slider.configure(state='normal')
        PEQ2_qfactor_slider.configure(state='normal')
        PEQ2_checkbox.configure(text='PEQ2 Enabled')
    elif not(PEQ2_var.get()) and 'Disabled' not in PEQ2_checkbox.cget("text"):
        PEQ2_freq_slider.configure(state='disabled')
        PEQ2_boost_slider.configure(state='disabled')
        PEQ2_qfactor_slider.configure(state='disabled')
        PEQ2_checkbox.configure(text='PEQ2 Disabled')
    if PEQ3_var.get() and 'Enabled' not in PEQ3_checkbox.cget("text"):
        PEQ3_freq_slider.configure(state='normal')
        PEQ3_boost_slider.configure(state='normal')
        PEQ3_qfactor_slider.configure(state='normal')
        PEQ3_checkbox.configure(text='PEQ3 Enabled')
    elif not(PEQ3_var.get()) and 'Disabled' not in PEQ3_checkbox.cget("text"):
        PEQ3_freq_slider.configure(state='disabled')
        PEQ3_boost_slider.configure(state='disabled')
        PEQ3_qfactor_slider.configure(state='disabled')
        PEQ3_checkbox.configure(text='PEQ3 Disabled')
    if room_gain_var.get() and 'ON' not in room_gain_checkbox.cget("text"):
        room_gain_slider.configure(state='normal')
        room_gain_slope_combo.configure(state='readonly')
        room_gain_checkbox.configure(text='Room Gain Compensation ON')
    elif not(room_gain_var.get()) and 'OFF' not in room_gain_checkbox.cget("text"):
        room_gain_slider.configure(state='disabled')
        room_gain_slope_combo.configure(state='disabled')
        room_gain_checkbox.configure(text='Room Gain Compensation OFF')
    if not(polarity_var.get()) and '(+)' not in polarity_checkbox.cget("text"):
        polarity_checkbox.configure(text='Polarity (+)')
    elif polarity_var.get() and '(-)' not in polarity_checkbox.cget("text"):
        polarity_checkbox.configure(text='Polarity (-)')
    return

def on_closing():
    global RUN_THREAD
    RUN_THREAD = False
    if GUI:
        window.destroy()
        print("Exiting...")
    while True: sys.exit(0)

###################    End GUI Routines    ###################

###################    main()    ###################

def show_usage():
    print('\npySVS ' + VERSION + '. Read and set SVS SB1000P Subwoofer values. By Logon84 http://github.com/logon84')
    print('Run pySVS.py without arguments to launch the GUI')
    print('USAGE: pySVS.py <-b device> <-m MAC_Address> <parameter1> <value1> <parameter2> <value2> etc...')
    print('\n-b dev or --btdevice=dev: Specify a different BT device to use (default is hci0).')
    print('-m MAC or --mac=MAC: Sets a mac address different to the one set in pySVS.py file.')
    print('-h or --help: Show this help.')
    print('-v or --version: Show program version.')
    print('-e or --encode: Just print built frames based on param values.')
    print('-d FRAME or --decode=FRAME: Decode values of a frame.')
    print('\nPARAMETER LIST:')
    print('\t-l X@Y@Z or --lpf=X@Y@Z: Sets Low Pass Filter to X[0(OFF),1(ON)], Y[freq] and Z[slope].')
    print('\t-q V@W@X@Y@Z or --peq=V@W@X@Y@Z: Sets PEQ V[1..3], W[0(OFF),1(ON)], X[freq], Y[boost] and Z[Qfactor].')
    print('\t-r X@Y@Z or --roomgain=X@Y@Z: Sets RoomGain X[0(OFF),1(ON)], Y[freq] and Z[slope].')
    print('\t-o X or --volume=X: Sets volume level to X on subwoofer.')
    print('\t-f X or --phase=X: Sets phase level to X on subwoofer.')
    print('\t-k X or --polarity=X: Sets polarity to 0(+) or 1(-) on subwoofer.')
    print('\t-p X or --preset=X: Load preset X[1..4(FACTORY DEFAULT PRESET)] on subwoofer.')
    print('\tTo ask subwoofer for one or more values, set parameter value to \"A\".\n')
    return

if __name__ == "__main__":
    VERSION = "v3.0 Beta"
    dev="hci0"
    if len(sys.argv[1:]) > 0:
        GUI = 0
        param_values = {}
        encode=0
        try:
            options, arguments = getopt.getopt(sys.argv[1:],"b:m:hved:l:q:r:o:f:k:p:",["btdevice=","mac=","help","version","encode","decode=","lpf=","peq=","roomgain=","volume=", "phase=", "polarity=", "preset="])
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
            if opt in ("-h", "--help"):
                show_usage()
                sys.exit(0)
            if opt in ("-v", "--version"):
                print(VERSION)
                sys.exit(0)
            if opt in ("-b", "--btdevice"):
                dev=opt_val
            if opt in ("-e", "--encode"):
                encode=1
            if opt in ("-d", "--decode"):
                print(svs_decode(unhexlify(opt_val.replace("0x",""))))
                sys.exit(0)
            if opt in ("-l", "--lpf"):
                if len(opt_val.split("@")) == 3:
                    sub_params = ["LPF_ENABLE","LOW_PASS_FILTER_FREQ","LOW_PASS_FILTER_SLOPE"]
                    for i in range(0,3):
                        if len(opt_val.split("@")[i]) > 0:
                            param_values[sub_params[i]] = [None] if opt_val.split("@")[i].upper() == 'A' else [int(float(opt_val.split("@")[i]))]
                else:
                    print("ERROR: Values for LPF incorrect")
                    print("Examples of correct values: 1@@12, 0@50@12, A@@6")
                    sys.exit(1)
            if opt in ("-q", "--peq"):
                if len(opt_val.split("@")) == 5:
                    peq_number = opt_val.split("@")[0]
                    if int(peq_number) in range(1,4):
                        sub_params = ["PEQ" + peq_number + "_ENABLE","PEQ" + peq_number + "_FREQ","PEQ" + peq_number + "_BOOST","PEQ" + peq_number + "_QFACTOR"]
                        for i in range(1,5):
                            if len(opt_val.split("@")[i]) > 0:
                                param_values[sub_params[i-1]] = [None] if opt_val.split("@")[i].upper() == 'A' else [float(opt_val.split("@")[i])]
                    else:
                        print("ERROR: PEQ profile number incorrect")
                        sys.exit(1)
                else:
                    print("ERROR: Values for PEQ incorrect")
                    print("Examples of correct values: 2@1@@@0.2, 3@0@40@-11.5@10, 1@A@@@")
                    sys.exit(2)
            if opt in ("-r", "--roomgain"):
                if len(opt_val.split("@")) == 3:
                    for i in range(0,3):
                        sub_params = ["ROOM_GAIN_ENABLE","ROOM_GAIN_FREQ","ROOM_GAIN_SLOPE"]
                        if len(opt_val.split("@")[i]) > 0:
                            param_values[sub_params[i]] = [None] if opt_val.split("@")[i].upper() == 'A' else [int(float(opt_val.split("@")[i]))]
                else:
                    print("ERROR: Values for Roomgain incorrect")
                    print("Examples of correct values: 1@@12, 0@31@12, A@@6")
                    sys.exit(1)
            if opt in ("-o", "--volume"):
                param_values["VOLUME"] = [None] if opt_val.upper() == 'A' else [int(float(opt_val))]
            if opt in ("-f", "--phase"):
                param_values["PHASE"] = [None] if opt_val.upper() == 'A' else [int(float(opt_val))]
            if opt in ("-k", "--polarity"):
                param_values["POLARITY"] = [None] if opt_val.upper() == 'A' else [int(float(opt_val))]
            if opt in ("-p", "--preset"):
                if int(opt_val) in range (1,5): 
                    param_values["PRESET" + opt_val + "LOAD"] = [None]
                else:
                    print("ERROR: Incorrect preset number specified")
        try:
            operands = [int(arg) for arg in arguments]
        except ValueError:
            show_usage()
            sys.exit(2)
            raise SystemExit()

        if len(param_values) > 0:
            #validate values
            for param in param_values.keys():
                if param_values[param][0] is None:
                    check = True
                elif type(param_values[param][0]) == str:
                    check = SVS_PARAMS[param]["limits_type"] == 2
                else:
                    if SVS_PARAMS[param]["limits_type"] == 1:
                        check = param_values[param][0] in SVS_PARAMS[param]["limits"]
                    elif SVS_PARAMS[param]["limits_type"] == 0:
                        check = max(SVS_PARAMS[param]["limits"]) >= param_values[param][0] >= min(SVS_PARAMS[param]["limits"])
                
                if not check:
                    print("ERROR: Value for %s incorrect" % (param))
                    sys.exit(1)

            #merge params if possible
            bytes_left = 0
            for key in SVS_PARAMS.keys():
                if SVS_PARAMS[key]["limits_type"] == "group":
                    key_to_merge = key
                    params_to_merge = []
                    bytes_left = SVS_PARAMS[key]["n_bytes"]
                    data_types = []
                    out = []
                elif bytes_left > 0:
                    if key in param_values.keys():
                        data_types.append(None if param_values[key][0] is None else str(param_values[key][0]).replace(".","",1).isnumeric())
                        merge = 1 if len(data_types) == 1 else merge*int(data_types[len(data_types)-1] == data_types[len(data_types)- 2])
                        if merge:
                            bytes_left = bytes_left - SVS_PARAMS[key]["n_bytes"]
                            params_to_merge.append(key)
                            if bytes_left == 0:
                                for param in params_to_merge:
                                    out = out + param_values[param]
                                    del param_values[param]
                                param_values.update({key_to_merge:out})
                        else:
                            #cancel merge operation
                            bytes_left = 0
                    else:
                        #cancel merge operation
                        bytes_left = 0

            if encode:
                for param in param_values.keys():
                    if param_values[param][0] is None:
                        if "PRESET" in param:
                            print(bytes2hexstr(svs_encode("PRESETLOADSAVE",param)[0]))
                        else:
                            print(bytes2hexstr(svs_encode("MEMREAD",param)[0]))
                    else:
                        print(bytes2hexstr(svs_encode("MEMWRITE",param,param_values[param])[0]))
                sys.exit(0)
            else:
                threading()
                for param in param_values.keys():
                    if param_values[param][0] is None:
                        if "PRESET" in param:
                            TX.BUFFER=TX.BUFFER + svs_encode("PRESETLOADSAVE", param)
                        else:
                            TX.BUFFER=TX.BUFFER + svs_encode("MEMREAD", param)
                    else:
                        TX.BUFFER=TX.BUFFER + svs_encode("MEMWRITE", param, param_values[param])
                while len(TX.BUFFER) > 0: pass
                time.sleep(0.5)
                on_closing()
        else:
            print("Nothing to do!")
            sys.exit(0)

    else:
        show_usage()
        GUI = 1
        try:
            window = tk.Tk()
            window.protocol("WM_DELETE_WINDOW", on_closing)
            window.title("pySVS " + VERSION + " - SVS Subwoofer Control")
            window.geometry('570x400')
            window.resizable(False, False)
            style= ttk.Style()
            style.map("TCombobox", fieldbackground=[("readonly", "white"),("disabled", "gray") ])
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

            vol_slider = tk.Scale(tab1, from_=min(SVS_PARAMS["VOLUME"]["limits"]), to=max(SVS_PARAMS["VOLUME"]["limits"]), label = "Volume (dB)", orient=tk.HORIZONTAL, resolution=1 if type(SVS_PARAMS["PHASE"]["limits"][0]) == int else 0.1, length=200)
            vol_slider.grid(column=4, row=3, padx = 20, pady = 15)
            vol_slider.bind("<ButtonRelease-1>", update_vol)

            phase_slider = tk.Scale(tab1, from_=min(SVS_PARAMS["PHASE"]["limits"]), to=max(SVS_PARAMS["PHASE"]["limits"]), label = "Phase (°)", orient=tk.HORIZONTAL, resolution=1 if type(SVS_PARAMS["PHASE"]["limits"][0]) == int else 0.1, length=200)
            phase_slider.grid(column=4, row=5, padx = 20, pady = 15)
            phase_slider.bind("<ButtonRelease-1>", update_phase)

            lpfilter_slider = tk.Scale(tab1, from_=min(SVS_PARAMS["LOW_PASS_FILTER_FREQ"]["limits"]), to=max(SVS_PARAMS["LOW_PASS_FILTER_FREQ"]["limits"]), label = "Low Pass Filter Freq. (Hz)", orient=tk.HORIZONTAL, resolution=1 if type(SVS_PARAMS["LOW_PASS_FILTER_FREQ"]["limits"][0]) == int else 0.1, length=200)
            lpfilter_slider.grid(column=4, row=7, padx = 20, pady = 15)
            lpfilter_slider.bind("<ButtonRelease-1>", update_lpfilter_freq)
            lpfilter_slope_combo=ttk.Combobox(tab1,values=[str(l) + " dB" for l in SVS_PARAMS["LOW_PASS_FILTER_SLOPE"]["limits"]],width=7,state='readonly')
            lpfilter_slope_combo.grid(sticky="W",column=5, row=7)
            lpfilter_slope_combo.bind("<<ComboboxSelected>>", update_lpfilter_slope)
            lpf_var = tk.BooleanVar(value=False)
            lpf_checkbox = ttk.Checkbutton(tab1, variable=lpf_var, command=lpf_opt_changed)
            lpf_checkbox.place(x=325,y=218)

            room_gain_slider = tk.Scale(tab1, from_=min(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"]), to=max(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"]), label = "Room Gain Freq. (Hz)", orient=tk.HORIZONTAL, resolution=1 if type(SVS_PARAMS["ROOM_GAIN_FREQ"]["limits"][0]) == int else 0.1, length=200, command=make_room_gain__freq_discrete_slider)
            room_gain_slider.bind("<ButtonRelease-1>", update_room_gain_freq)
            room_gain_slider.grid(column=4, row=9, padx = 20, pady = 15)
            room_gain_slope_combo=ttk.Combobox(tab1,values=[str(l) + " dB" for l in SVS_PARAMS["ROOM_GAIN_SLOPE"]["limits"]],width=7,state='readonly')
            room_gain_slope_combo.grid(sticky="W",column=5, row=9)
            room_gain_slope_combo.bind("<<ComboboxSelected>>", update_room_gain_slope)
            room_gain_var = tk.BooleanVar(value=True)
            room_gain_checkbox = ttk.Checkbutton(tab1, variable=room_gain_var, command=room_gain_opt_changed)
            room_gain_checkbox.place(x=326,y=310)

            try:
                subwoofer = Image.open(requests.get("https://i.imgur.com/qX85CCG.jpg", stream=True).raw)
                subwoofer = subwoofer.resize((200, 200))
                subwoofer = ImageTk.PhotoImage(subwoofer)
                picframe = tk.Label(tab1, image = subwoofer)
                picframe.grid(sticky="NW", column=5, row=0, columnspan=9, rowspan=9, padx=50)
            except:
                pass
            
            PEQ1_var = tk.IntVar(value=0)
            PEQ1_checkbox = ttk.Checkbutton(tab2, variable=PEQ1_var, text='PEQ1', command=peq1_opt_changed)
            PEQ1_checkbox.place(x=40,y=15)
            PEQ1_freq_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ1_FREQ"]["limits"]), to=max(SVS_PARAMS["PEQ1_FREQ"]["limits"]), label = "Freq (Hz)", orient=tk.HORIZONTAL, resolution=1 if type(SVS_PARAMS["PEQ1_FREQ"]["limits"][0]) == int else 0.1, length=100)
            PEQ1_freq_slider.bind("<ButtonRelease-1>", update_peq1_freq)
            PEQ1_freq_slider.grid(column=7, row=3, padx = 35, pady = 35)
            PEQ1_boost_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ1_BOOST"]["limits"]), to=max(SVS_PARAMS["PEQ1_BOOST"]["limits"]), label = "Boost (dB)", orient=tk.HORIZONTAL, resolution=1 if type(SVS_PARAMS["PEQ1_BOOST"]["limits"][0]) == int else 0.1, length=100)
            PEQ1_boost_slider.bind("<ButtonRelease-1>", update_peq1_boost)
            PEQ1_boost_slider.grid(column=7, row=5, padx = 20, pady = 15)
            PEQ1_qfactor_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ1_QFACTOR"]["limits"]), to=max(SVS_PARAMS["PEQ1_QFACTOR"]["limits"]), label = "Q-Factor", orient=tk.HORIZONTAL, resolution=1 if type(SVS_PARAMS["PEQ1_QFACTOR"]["limits"][0]) == int else 0.1, length=100)
            PEQ1_qfactor_slider.bind("<ButtonRelease-1>", update_peq1_qfactor)
            PEQ1_qfactor_slider.grid(column=7, row=7, padx = 20, pady = 35)

            PEQ2_var = tk.IntVar(value=0)
            PEQ2_checkbox = ttk.Checkbutton(tab2, variable=PEQ2_var, text='PEQ2', command=peq2_opt_changed)
            PEQ2_checkbox.place(x=215,y=15)
            PEQ2_freq_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ2_FREQ"]["limits"]), to=max(SVS_PARAMS["PEQ2_FREQ"]["limits"]), label = "Freq (Hz)", orient=tk.HORIZONTAL, resolution=1 if type(SVS_PARAMS["PEQ2_FREQ"]["limits"][0]) == int else 0.1, length=100)
            PEQ2_freq_slider.bind("<ButtonRelease-1>", update_peq2_freq)
            PEQ2_freq_slider.grid(column=8, row=3, padx = 35, pady = 35)
            PEQ2_boost_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ2_BOOST"]["limits"]), to=max(SVS_PARAMS["PEQ2_BOOST"]["limits"]), label = "Boost (dB)", orient=tk.HORIZONTAL, resolution=1 if type(SVS_PARAMS["PEQ2_BOOST"]["limits"][0]) == int else 0.1, length=100)
            PEQ2_boost_slider.bind("<ButtonRelease-1>", update_peq2_boost)
            PEQ2_boost_slider.grid(column=8, row=5, padx = 20, pady = 15)
            PEQ2_qfactor_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ2_QFACTOR"]["limits"]), to=max(SVS_PARAMS["PEQ2_QFACTOR"]["limits"]), label = "Q-Factor", orient=tk.HORIZONTAL, resolution=1 if type(SVS_PARAMS["PEQ2_QFACTOR"]["limits"][0]) == int else 0.1, length=100)
            PEQ2_qfactor_slider.bind("<ButtonRelease-1>", update_peq2_qfactor)
            PEQ2_qfactor_slider.grid(column=8, row=7, padx = 20, pady = 35)

            PEQ3_var = tk.IntVar(value=0)
            PEQ3_checkbox = ttk.Checkbutton(tab2, variable=PEQ3_var, text='PEQ3', command=peq3_opt_changed)
            PEQ3_checkbox.place(x=390,y=15)
            PEQ3_freq_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ3_FREQ"]["limits"]), to=max(SVS_PARAMS["PEQ3_FREQ"]["limits"]), label = "Freq (Hz)", orient=tk.HORIZONTAL, resolution=1 if type(SVS_PARAMS["PEQ3_FREQ"]["limits"][0]) == int else 0.1, length=100)
            PEQ3_freq_slider.bind("<ButtonRelease-1>", update_peq3_freq)
            PEQ3_freq_slider.grid(column=9, row=3, padx = 35, pady = 35)
            PEQ3_boost_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ3_BOOST"]["limits"]), to=max(SVS_PARAMS["PEQ3_BOOST"]["limits"]), label = "Boost (dB)", orient=tk.HORIZONTAL, resolution=1 if type(SVS_PARAMS["PEQ3_BOOST"]["limits"][0]) == int else 0.1, length=100)
            PEQ3_boost_slider.bind("<ButtonRelease-1>", update_peq3_boost)
            PEQ3_boost_slider.grid(column=9, row=5, padx = 20, pady = 15)
            PEQ3_qfactor_slider = tk.Scale(tab2, from_=min(SVS_PARAMS["PEQ3_QFACTOR"]["limits"]), to=max(SVS_PARAMS["PEQ3_QFACTOR"]["limits"]), label = "Q-Factor", orient=tk.HORIZONTAL, resolution=1 if type(SVS_PARAMS["PEQ3_QFACTOR"]["limits"][0]) == int else 0.1, length=100)
            PEQ3_qfactor_slider.bind("<ButtonRelease-1>", update_peq3_qfactor)
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
            autoon_values = ["AUTO ON","TRIIGER","ON"]
            autoon_combo = ttk.Combobox(tab3,values=autoon_values,width=7,state='readonly')
            autoon_combo.bind("<<ComboboxSelected>>", autoon_combo_changed)
            autoon_combo.grid(sticky="W",column=1, row=4, padx=30, ipadx = 20)
            autoon_combo.current(1)

            polarity_var = tk.BooleanVar(value=1)
            polarity_checkbox = ttk.Checkbutton(tab3, variable=polarity_var, command=polarity_opt_changed, text='Polarity')
            polarity_checkbox.place(x=25,y=180)
            
            threading()
            window.mainloop()

        except Exception:
            traceback.print_exc()

###################    End main()    ###################
