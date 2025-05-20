from pythonosc import udp_client
import requests
import time
import sys
import queue
import serial
import threading

# Resource settings
emoQueue = queue.Queue()
canSwitchEmotion = True
enforceSwitchEmotion = False
emotionChangedFlag = False
currentEmotion = -1
emoTransTimer = -1
lastEffectNum = -2

# Line Bot settings
SERVER_URL = "https://5c77-140-118-176-226.ngrok-free.app/fetch"
TIMEOUT = 5

# Arduino settings
SERIAL_PORT = 'COM5'  
BAUD_RATE = 9600

arduino_data = -1
isNearMuuLast = False
isNearMuu = False
noBodyNearTimer = -1

FILTER_WINDOW_SIZE = 5
distance_readings = []

try:
    arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    print(f"Connected to Arduino on {SERIAL_PORT} at {BAUD_RATE} baud.")
    if arduino:
        print("Arduino connected")
except serial.SerialException as e:
    print(f"Error connecting to Arduino: {e}")
    arduino = None 
    

# Resolume Arena settings
try:
    client = udp_client.SimpleUDPClient("127.0.0.1", 7000) 
    print("Connected to Resolume at 127.0.0.1:7000")
except Exception as e:
    print(f"Error connecting to Resolume: {e}")
    client = None


def line_bot_fetch_thread():
    global emoQueue
    while True:
        try:
            res = requests.get(SERVER_URL, timeout=TIMEOUT)
            
            if res.status_code == 204:
                print("No update data available in server (204)")
            elif res.status_code == 200:
                data = res.json().get("data", [])
                if data:
                    print(f"Received data from Line Bot: {data}")
                    for num_str in data:
                        try:
                            emoQueue.put(int(num_str))
                        except ValueError:
                            print(f"Warning: Could not convert '{num_str}' to int from Line Bot data.")
                else:
                    print("Empty data from Line Bot")
            else:
                print(f"Line Bot Server returned status code: {res.status_code}")
        except requests.exceptions.Timeout:
            print(f"Line Bot connection timed out after {TIMEOUT} seconds")
        except requests.exceptions.ConnectionError:
            print("Line Bot connection error - check if ngrok is running and URL is correct")
        except Exception as e:
            print(f"Error in Line Bot thread: {type(e).__name__}: {e}")
        time.sleep(1) 

def arduino_read_thread():
    global arduino, isNearMuu, arduino_data, distance_readings, FILTER_WINDOW_SIZE
    while True:
        if arduino:
            try:
                if arduino.in_waiting:
                    serial_data = arduino.readline().decode('utf-8').rstrip()
                    print(f"Received from Arduino: {serial_data}")
                    if serial_data != "":
                        current_reading = float(serial_data)
                        
                        '''
                        if current_reading == -1:
                            arduino_data = -1
                            continue
'''
                        distance_readings.append(current_reading)
                        if len(distance_readings) > FILTER_WINDOW_SIZE:
                            distance_readings.pop(0)
                        
                        if distance_readings:
                            arduino_data = sum(distance_readings) / len(distance_readings)
                        else:
                            arduino_data = current_reading 
                    
            except serial.SerialException as e:
                arduino_data = -1
                print(f"Error reading from Arduino: {e}")
                time.sleep(1) 
            except UnicodeDecodeError as e:
                print(f"Error decoding Arduino data: {e}")
            except Exception as e:
                print(f"Error in Arduino thread: {type(e).__name__}: {e}")
        else:
            time.sleep(1) 
            
        time.sleep(0.2) 
        
def effect(emotion, isBurst=False):
    global client, emotionChangedFlag
    if emotion == -1:
        emotionChangedFlag = True
        client.send_message("/composition/layers/2/clear", 1)
        client.send_message("/composition/layers/2/clear", 0)
        client.send_message("/composition/layers/1/clips/1/transport/position/behaviour/playmode", 0)
    else:
        emotionChangedFlag = False
        client.send_message(f"/composition/layers/1/clips/{emotion + 2}/transport/position/behaviour/playmode", 4)
        
    if emotion == 4 and not isBurst:
        client.send_message("/composition/layers/1/clips/7/connect", 1) # switch to white solid color
        client.send_message("/composition/layers/2/clips/4/connect", 1) # switch to burst     
        time.sleep(1.5)
        
    if emotion != 4:
        client.send_message("/composition/layers/2/clear", 1)
        client.send_message("/composition/layers/2/clear", 0)


def switchEmotion(emotion):
    global client, emotionChangedFlag
    if client:
        effect(emotion)
        client.send_message(f"/composition/layers/1/clips/{emotion + 2}/connect",  1)  
        print(f"Switching to emotion: {emotion}")
    else:
        print("Resolume connection error")
            

def someoneComesIn(emotion):
    # TODO: switch to current emotion after burst
    # client.send_message("/composition/layers/1/clips/7/connect", 1) # switch to white solid color
    client.send_message("/composition/layers/2/clips/4/connect", 1) # switch to burst     
    time.sleep(0.6) 
    client.send_message("/composition/layers/2/clear", 1)
    client.send_message("/composition/layers/2/clear", 0)

    effect(emotion, isBurst=True)


line_bot_thread = threading.Thread(target=line_bot_fetch_thread, daemon=True)
line_bot_thread.start()

arduino_thread = threading.Thread(target=arduino_read_thread, daemon=True)
arduino_thread.start()

client.send_message("/composition/layers/2/clear", 1)
client.send_message("/composition/layers/2/clear", 0)
client.send_message("/composition/layers/1/clips/1/connect", 1)
client.send_message("/composition/layers/1/clips/1/transport/position/behaviour/playmode", 0)

    
while True:
    try:
        now = time.time()
        if emoTransTimer != -1 and now - emoTransTimer >= 10:
            enforceSwitchEmotion = True
            canSwitchEmotion = True
        elif emoTransTimer != -1 and now - emoTransTimer >= 5:
            canSwitchEmotion = True
        
        if arduino_data == -1:
            isNearMuu = False
        else:
            isNearMuu = True
            
        # someone near MUU
        if isNearMuuLast != isNearMuu:
            if not isNearMuu and noBodyNearTimer == -1:
                noBodyNearTimer = time.time()
            elif isNearMuu:
                if noBodyNearTimer != -1:
                    noBodyNearTimer = -1
                someoneComesIn(currentEmotion)
            isNearMuuLast = isNearMuu
        elif not isNearMuu:
            if noBodyNearTimer != -1 and now - noBodyNearTimer > 10:
                print("Can switch emotion trun on")
                enforceSwitchEmotion = True
                  
        # switch emotion 
        if enforceSwitchEmotion or (canSwitchEmotion and not isNearMuu):
            if emoQueue.empty(): 
                if currentEmotion != -1:
                    emotionChangedFlag = True
                else:
                    emotionChangedFlag = False
                currentEmotion = -1 
            else:
                lastEmotion = currentEmotion
                currentEmotion = emoQueue.get()
                
                if lastEmotion != currentEmotion:
                    emotionChangedFlag = True
                else:
                    emotionChangedFlag = False
            
            emoTransTimer = time.time()
            canSwitchEmotion = False
            enforceSwitchEmotion = False

        # calculate distance portion
        distance = arduino_data
        relativeDistance =  1 - distance / 500 # inside 0-1 range

        # effect apply when someone near MUU
        if isNearMuu and arduino_data >= 0:
            if currentEmotion == -1 and lastEffectNum != -1:
                print("Switch to -1")
                client.send_message("/composition/layers/2/clear", 1)
                client.send_message("/composition/layers/2/clear", 0)
                lastEffectNum = -1
                
            elif currentEmotion == 0 and lastEffectNum != 0:
                # TODO: corresponding effect
                lastEffectNum = 0
                pass
                
            elif currentEmotion == 1 and lastEffectNum != 1:
                client.send_message("/composition/layers/2/clips/2/connect", 1) # switch to fast sparkle
                speed = 0.5 + relativeDistance
                client.send_message("/composition/layers/2/clips/2/transport/position/behaviour/speed", speed)
                lastEffectNum = 1
                
            elif currentEmotion == 2 and lastEffectNum != 2:
                client.send_message("/composition/layers/2/clips/1/connect", 1) # switch to slow sparkle
                speed = min(2.2 - relativeDistance * 1.3, 0.9)
                client.send_message("/composition/layers/2/clips/1/transport/position/behaviour/speed", speed)
                lastEffectNum = 2
                
            elif currentEmotion == 3 and lastEffectNum != 3:
                client.send_message("/composition/layers/2/clips/3/connect", 1) # switch to fast soft sparkle
                speed = 0.8 + relativeDistance * 0.9
                print(f"Speed: {speed}")
                client.send_message("/composition/layers/2/clips/3/transport/position/behaviour/speed", speed)
                lastEffectNum = 3
        else:
            client.send_message("/composition/layers/2/clear", 1)
            client.send_message("/composition/layers/2/clear", 0)
                
                    
        if emotionChangedFlag:
            print(f"Switching to emotion: {currentEmotion}")
            switchEmotion(currentEmotion)           
        
                    
    except requests.exceptions.Timeout:
        print(f"Connection timed out after {TIMEOUT} seconds")
    except requests.exceptions.ConnectionError:
        print("Connection error - check if ngrok is running and URL is correct")
    except serial.SerialException as e:
        print(f"Arduino communication error: {e}")
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
    
    time.sleep(0.01) 
