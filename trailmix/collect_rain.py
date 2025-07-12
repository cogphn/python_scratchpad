import pandas as pd
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup, SoupStrainer
from tqdm import tqdm

URI_TMPL = "https://dd.weather.gc.ca/__dt__/WXO-DD/observations/swob-ml/partners/on_water/__dt__/"


class GenericResponse:
    response_code: int
    message: str
    data = {}
    errors = []
    def __init__(self, response_code, message, data, errors):
        self.response_code = response_code
        self.message = message
        self.data = data
        self.errors = errors
#

def readData(url:str):
    resp = requests.get(url)
    soup = BeautifulSoup(resp.text, features="xml")
    metadata = soup.find("om:metadata")
    result = soup.find("om:result")
    metadata_transformed = {}
    data_transformed = []
    for m in metadata.findAll("element"):
        if m.has_attr("name"):
            metadata_transformed[m["name"]] = m["value"]

    for r in result.find():
        if r.has_attr("name"):
            data_row = {}
            data_row["name"] = r["name"]
            data_row["value"] = r["value"]
            data_row["uom"] = r["uom"]
            data_row["lat"] = metadata_transformed["lat"]
            data_row["long"] = metadata_transformed["long"]
            data_row["stn_id"] = metadata_transformed["stn_id"]
            data_row["date_tm"] = metadata_transformed["date_tm"]
            data_transformed.append(data_row)
    ret = { "metadata": metadata_transformed, "data": data_transformed }
    return ret

#

def getSubLinks(url:str):
    resp = requests.get(url)
    obj = BeautifulSoup(resp.text, parse_only=SoupStrainer("a"))
    sublinks = [url + link["href"].strip() for link in obj if link["href"].startswith("wsc")]
    ret = sublinks
    return ret
#

def getDataLinks(url:str):
    resp = requests.get(url)
    obj = BeautifulSoup(resp.text, parse_only=SoupStrainer("a"))
    datalinks = [url + link["href"].strip() for link in obj if link["href"].endswith("xml")]
    ret = datalinks
    return ret

def getUrlListForPeriod(start_date: datetime, end_date: datetime):
    if end_date < start_date:
        return GenericResponse(
                response_code = -1,
                message = "invalid arguments",
                errors = ["end date before start date"]
                )
    current_date_s = start_date.strftime("%Y%m%d") 
    end_date_s = end_date.strftime("%Y%m%d")
    urllist = []
    d = 1
    while current_date_s != end_date_s:
        urllist.append(URI_TMPL.replace("__dt__",current_date_s))
        current_date_s = (start_date + timedelta(days = d)).strftime("%Y%m%d")
        d += 1
    return urllist


def run():
    # 5 day window
    start_date = datetime.now() - timedelta(days=5)
    end_date = datetime.now() + timedelta(days=1)

    print(f"    [*] start_date: {start_date}, end_date: {end_date}")

    urls_for_period = getUrlListForPeriod(start_date, end_date)
    data = []
    for url in tqdm(urls_for_period):
        sublinks = getSubLinks(url)
        for link in tqdm(sublinks):
            datalinks = getDataLinks(link)
            for datalink in datalinks:
                row = {}
                row["baseurl"] = url
                row["sublink"] = link
                row["datalink"] = datalink
                data.append(row)
            #
    # get station data
    alldata = None
    print("    [*] getting data....")
    
    for d in tqdm(data):
        station_data = readData(d["datalink"])
        df = pd.DataFrame(station_data['data'])
        if alldata is None:
            alldata = df
        else:
            alldata = pd.concat([alldata,df]).copy()
        #
    return alldata
#

if __name__ == "__main__":
    print("[*] starting...")
    run()
    print("[.] done")
#
