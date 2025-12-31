print("[*] starting...")

import cv2
import time as p_tm
import os

from datetime import datetime, timedelta
#import discord
#from discord.ext import commands
####from discord import Webhook
#from discord_webhook import DiscordWebhook
from threading import Thread
import requests
import os
import json

'''
{
  "webhook_url":"",
  "t_token":"",
  "t_chatid":"",
  "img_path":""
}
'''


config  = {}
with open("md3.config.json") as configfile:
    config_str = configfile.read()
    config = json.loads(config_str)

webhook_url = config["webhook_url"]
t_token = config["t_token"]
t_chatid = config["t_chatid"]
t_send_uri = f"https://api.telegram.org/bot{t_token}/sendPhoto?chat_id={t_chatid}"


def getnow():
    dtnow = datetime.now()
    dtnow_str = dtnow.strftime("%Y-%m-%d %H:%M:%S")
    return dtnow_str
#

# Assigning our static_back to None
static_back = None

# Time of movement
time = []

# Initializing DataFrame, one column is start
# time and other column is end time

# Capturing video
video = cv2.VideoCapture(0)

img_path = "/media/lh3/motiondetect"
window = 10


def send_notification(imgfilename):
	##webhook = DiscordWebhook(url=webhook_url)
	#with open(imgfilename, "rb") as img:
	#	#webhook.add_file(file=img.read(), filename="capture.png")
	#	#requests.post(t_send_uri, files={"photo":img})
	#	webhook.add_file(file=img.read(), filename="capture.png")
	#resp = webhook.execute()
	try:
		with open(imgfilename, "rb") as img:
			resp = requests.post(t_send_uri, files={"photo":img})
		# print(resp) # DBG
	except Exception as e:
		print("[!] error sending to telegram :-("+str(e))
	#
	os.remove(imgfilename) #sent file, safe to delete within the same thread
	
# I believe I took the bulk of this code from "https://siddharthmehta.in/blog/2020/motion-detection-using-opencv/"
print("[*] running...")
while True:
    try:
        check, frame = video.read()
        motion = 0
        # Converting color image to gray_scale image
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Converting gray scale image to GaussianBlur
        # so that change can be find easily
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        # In first iteration we assign the value
        # of static_back to our first frame
        if static_back is None:
            static_back = gray
            continue

        # Difference between static background
        # and current frame(which is GaussianBlur)
        diff_frame = cv2.absdiff(static_back, gray)

        # If change in between static background and
        # current frame is greater than 30 it will show white color(255)
        thresh_frame = cv2.threshold(diff_frame, 30, 255, cv2.THRESH_BINARY)[1]
        thresh_frame = cv2.dilate(thresh_frame, None, iterations = 2)

        # Finding contour of moving object
        cnts,_ = cv2.findContours(thresh_frame.copy(),cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in cnts:
            if cv2.contourArea(contour) < 10000:
                continue
            motion = 1
            (x, y, w, h) = cv2.boundingRect(contour)
            imgname = img_path+os.sep+"movement_"+datetime.now().strftime("%Y-%m-%d_%H_%M_%S_%f")+".png"
            static_back = gray
            cv2.imwrite(imgname,frame)
            p_tm.sleep(5)
            t=Thread(target=send_notification, args=[imgname])
            t.run()


        key = cv2.waitKey(1) # not sure if this works as expected, ctrl+c seems to work fine though 
        # q to quit
        if key == ord('q'):
            if motion == 1:
                time.append(datetime.now())
            break
    except KeyboardInterrupt:
        print("[!] ctrl+c received - shutting down...")
        break
    #
# end while 

# Appending time of motion in DataFrame
#for i in range(0, len(time), 2):
#	df = df.append({"Start":time[i], "End":time[i + 1]}, ignore_index = True)

video.release()
cv2.destroyAllWindows()
