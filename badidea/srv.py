from fastapi import FastAPI
from contextlib import asynccontextmanager
from pydantic import BaseModel
import superdb
import json
import os
from dotenv import load_dotenv
import importlib 
import asyncio
import pugsql
from datetime import datetime 


sdbclient = superdb.Client()


load_dotenv()
CONSTR = os.getenv('CONSTR')

queries = pugsql.module('queries')
queries.connect(CONSTR)


try:
    sdbclient.create_pool("temperature")
except Exception as e:
    print(f"[!] pool exists maybe idk: {e}")
#


class TempRecord(BaseModel):
    ts_utc: str
    ts_local: str
    temp_c: float
    temp_humidity_c: float
    temp_adjusted_c: float
#

class LabConfig(BaseModel):
    enabled: bool
#

class ConfigArgs(BaseModel):
    configname: str
    config: LabConfig 

def _get_config_names():
    config_names = [c['name'] for c in queries.get_configs()]
    return { "response_code": 0, "data": config_names }

def _get_config(config_name: str) -> dict:
    config = queries.get_config(name=config_name)
    return config
#

async def bgtasks():
    while True:
        print("[*] reloading modules (not implemented )...")
        #importlib.reload(bim)
        await asyncio.sleep(300)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[*] creating background task")
    asyncio.create_task(bgtasks())
    yield
    print("[!] shutting down...")
#


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def idx():
    return { "response_code": 0, "message": "running"}
#

@app.post("/rectemp")
async def record_temp(temprecord: TempRecord):
    record = { "ts_utc": temprecord.ts_utc, "ts_local": temprecord.ts_local, "temp_c": temprecord.temp_c, "temp_humidity_c": temprecord.temp_humidity_c, "temp_adjusted_c": temprecord.temp_adjusted_c }
    sdbclient.load("temperature", json.dumps(record))
    return temprecord
#

@app.get("/gettempdata")
async def get_tempdata():
    values = sdbclient.query('from temperature | sort -r ts_utc | limit 20')
    return values
#

@app.post("/reconfig")
async def reconfig(newconfig: ConfigArgs):
    args = json.dumps({"enabled":newconfig.config.enabled})
    config_name = newconfig.configname  
    reconfig_reg = queries.update_config(name=config_name, args=args)
    return { "response_code": 0, "data": reconfig_reg }


@app.get("/getconfig")
async def get_config(name: str = "NA"):
    if name == "NA":
        return {"response_code": 0, "data": {} }
    else:
        config = _get_config(name)
        return {"response_code": 0, "data": config}
    #
#


