import pandas as pd
import folium
import requests
data = pd.read_csv("rain.csv")
points = data[['lat','long']].drop_duplicates().to_dict(orient='records')
bikeresp = requests.get("https://tor.publicbikesystem.net/ube/gbfs/v1/en/station_information").json()
bikedata = pd.DataFrame(bikeresp['data']['stations'])
bikedata_trails = bikedata[bikedata['name'].str.lower().str.contains("trail")][['name','lat','lon','capacity','physical_configuration','is_charging_station']].copy().to_dict(orient="records")
bikedata_trails1 = bikedata[(bikedata['lat'] > 43.685493) & (bikedata['lon'] > -79.375279) & (bikedata['lat'] < 43.723941) & (bikedata['lon'] < -79.30183)][['name','lat','lon','capacity','physical_configuration','is_charging_station']].copy().to_dict(orient="records")


map = folium.Map(location=(43.701049, -79.353405), zoom_start=14)

for p in points:
  folium.Marker(
      location=[p['lat'], p['long']],
      icon=folium.Icon(icon='cloud'),
  ).add_to(map)

for station in bikedata_trails1:
  folium.Marker(
      location=[station['lat'],station['lon']],
      tooltip=station['capacity'],
      popup=station['name'],
      icon=folium.Icon(color="green"),
  ).add_to(map)


trail_coordinates = [
    (43.685493, -79.312214),
    (43.688047, -79.301830),
    (43.694960, -79.304812),
    (43.695208, -79.303257),
    (43.697566, -79.302752),
    (43.702484, -79.321667),
    (43.701840, -79.332278),
    (43.702957, -79.332396),
    (43.703182, -79.333812),
    (43.705850, -79.333244),
    (43.704880, -79.335486),
    (43.705842, -79.337074),
    (43.708867, -79.337417),
    (43.713070, -79.339670),
    (43.716172, -79.346698),
    (43.716141, -79.352105),
    (43.721212, -79.352556),
    (43.720103, -79.361536),
    (43.721491, -79.364422),
    (43.723530, -79.364862),
    (43.723941, -79.366621),
    (43.722716, -79.368992),
    (43.722352, -79.372490),
    (43.723089, -79.373702),
    (43.722786, -79.375279)
]

folium.PolyLine(trail_coordinates, tooltip="sbpath").add_to(map)
map
