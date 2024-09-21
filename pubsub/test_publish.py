import configparser
from google.cloud import pubsub_v1
import time
import os
import glob
import json

config = configparser.ConfigParser()
config.read("config.ini")
project_id = config['default']['project_id']
topic_id = config['default']['topic_id']
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = "creds.json"


if __name__ == "__main__":
    print("[*] starting...")

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, topic_id)
    srcfiles = glob.glob("transformed/*")
    for srcfile in srcfiles:
        with open(srcfile) as infile:
            for l in infile:
                data = json.dumps(l).encode("utf-8")
                future = publisher.publish(topic_path, data)
                print(future.result())
                time.sleep(300) # DBG
            #
        #
    #
