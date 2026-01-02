from fastapi import FastAPI
from pydantic import BaseModel
import superdb
import json

sdbclient = superdb.Client()
app = FastAPI()

try:
    sdbclient.create_pool("temperature")
except Exception as e:
    print("[!] pool exists maybe idk")
#

class TempRecord(BaseModel):
    ts_utc: str
    ts_local: str
    temp_c: float
    temp_humidity_c: float
    temp_adjusted_c: float
#

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



