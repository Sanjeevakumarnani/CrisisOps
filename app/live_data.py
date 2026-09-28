from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from functools import lru_cache
from math import radians, sin, cos, sqrt, atan2
from typing import Any

DEFAULT_LAT = 17.3850
DEFAULT_LON = 78.4867
DEFAULT_CITY = "Hyderabad, Telangana, India"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
USGS = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
IMD_CAP_RSS = "https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml"
GDACS = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
CACHE_TTL = 600

class LiveDataError(RuntimeError):
    pass

def _get(url: str, timeout: int = 12, retries: int = 2) -> bytes:
    headers = {"User-Agent": "CrisisOps/1.0", "Accept": "application/json, application/xml, text/xml, */*"}
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise

def _json(url: str) -> dict[str, Any]:
    return json.loads(_get(url).decode("utf-8"))

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r=6371.0; p1,p2=radians(lat1),radians(lat2); dp=radians(lat2-lat1); dl=radians(lon2-lon1)
    a=sin(dp/2)**2+cos(p1)*cos(p2)*sin(dl/2)**2
    return 2*r*atan2(sqrt(a),sqrt(1-a))

def weather(lat: float, lon: float) -> dict[str, Any]:
    params=urllib.parse.urlencode({"latitude":lat,"longitude":lon,"current":"temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_gusts_10m","hourly":"precipitation_probability,precipitation,wind_gusts_10m,visibility","forecast_days":2,"timezone":"auto"})
    data=_json(f"{OPEN_METEO}?{params}"); current=data.get("current",{}); hourly=data.get("hourly",{})
    times=hourly.get("time",[])
    return {"source":"Open-Meteo","source_url":"https://open-meteo.com/","location":{"latitude":lat,"longitude":lon,"timezone":data.get("timezone")},"observed_at":current.get("time"),"temperature_c":current.get("temperature_2m"),"apparent_temperature_c":current.get("apparent_temperature"),"humidity_pct":current.get("relative_humidity_2m"),"precipitation_mm":current.get("precipitation"),"wind_kmh":current.get("wind_speed_10m"),"gust_kmh":current.get("wind_gusts_10m"),"weather_code":current.get("weather_code"),"next_hours":[{"time":times[i],"precipitation_probability":hourly.get("precipitation_probability",[])[i],"precipitation_mm":hourly.get("precipitation",[])[i],"gust_kmh":hourly.get("wind_gusts_10m",[])[i]} for i in range(min(12,len(times)))]}

def usgs_quakes(lat: float, lon: float, radius_km: float=2500.0) -> list[dict[str,Any]]:
    data=_json(USGS); rows=[]
    for f in data.get("features",[]):
        p=f.get("properties",{}); coords=f.get("geometry",{}).get("coordinates",[])
        if len(coords)<2: continue
        qlon,qlat=coords[0],coords[1]; distance=_haversine_km(lat,lon,qlat,qlon)
        if distance<=radius_km and (p.get("mag") or 0)>=2.5:
            rows.append({"id":f.get("id"),"magnitude":p.get("mag"),"place":p.get("place"),"time":datetime.fromtimestamp((p.get("time") or 0)/1000,tz=timezone.utc).isoformat(),"latitude":qlat,"longitude":qlon,"depth_km":coords[2] if len(coords)>2 else None,"alert":p.get("alert"),"tsunami":bool(p.get("tsunami")),"url":p.get("url"),"distance_km":round(distance,1),"source":"USGS Earthquake Hazards Program"})
    rows.sort(key=lambda x:(x["magnitude"] or 0,-x["distance_km"]),reverse=True)
    return rows[:12]

def _parse_rss(raw: bytes) -> list[dict[str,Any]]:
    root=ET.fromstring(raw); items=[]
    for item in root.findall(".//item"):
        def txt(name):
            node=item.find(name); return (node.text or "").strip() if node is not None else ""
        items.append({"title":txt("title"),"description":txt("description"),"link":txt("link"),"published":txt("pubDate"),"guid":txt("guid"),"source":"India Meteorological Department CAP feed"})
    return items

def imd_alerts(limit:int=10) -> list[dict[str,Any]]:
    try: return _parse_rss(_get(IMD_CAP_RSS))[:limit]
    except Exception as exc: raise LiveDataError(f"IMD CAP feed unavailable: {exc}") from exc

def gdacs_events(lat: float, lon: float, limit:int=12, radius_km: float = 5000.0) -> list[dict[str,Any]]:
    today=datetime.now(timezone.utc).date()
    params=urllib.parse.urlencode({"eventlist":"EQ;TC;FL;DR;VO;WF","fromdate":str(today),"todate":str(today)})
    try: data=_json(f"{GDACS}?{params}")
    except Exception: return []
    rows=data if isinstance(data,list) else data.get("features",data.get("data",[])); out=[]
    for row in rows[:limit]:
        if not isinstance(row,dict): continue
        p=row.get("properties",row); g=row.get("geometry",{}); coords=g.get("coordinates",[]) if isinstance(g,dict) else []
        event_lat = coords[1] if len(coords) > 1 else p.get("lat")
        event_lon = coords[0] if len(coords) > 0 else p.get("lon")
        if event_lat is not None and event_lon is not None and _haversine_km(lat, lon, float(event_lat), float(event_lon)) > radius_km:
            continue
        out.append({"event_id":p.get("eventid") or p.get("eventId") or row.get("eventid"),"event_type":p.get("eventtype") or p.get("eventType") or p.get("event"),"name":p.get("name") or p.get("eventname") or p.get("eventName"),"alert_level":p.get("alertlevel") or p.get("alertLevel"),"country":p.get("country"),"latitude":event_lat,"longitude":event_lon,"source":"Global Disaster Alert and Coordination System (GDACS)"})
    return out

@lru_cache(maxsize=8)
def _cached(lat:float,lon:float,bucket:int)->dict[str,Any]:
    result={"generated_at":datetime.now(timezone.utc).isoformat(),"location":{"name":DEFAULT_CITY if round(lat,3)==round(DEFAULT_LAT,3) and round(lon,3)==round(DEFAULT_LON,3) else "Custom location","latitude":lat,"longitude":lon},"sources":[],"weather":None,"earthquakes":[],"imd_alerts":[],"gdacs_events":[],"errors":[]}
    for key,fn,src in [("weather",lambda:weather(lat,lon),"Open-Meteo"),("earthquakes",lambda:usgs_quakes(lat,lon),"USGS"),("imd_alerts",imd_alerts,"IMD CAP"),("gdacs_events",lambda:gdacs_events(lat,lon),"GDACS")]:
        try:
            result[key]=fn()
            if key!="gdacs_events" or result[key]: result["sources"].append(src)
        except Exception as exc:
            result["errors"].append(f"{key}: {exc}")
    return result

def get_live_data(lat:float=DEFAULT_LAT,lon:float=DEFAULT_LON)->dict[str,Any]:
    return _cached(float(lat),float(lon),int(time.time()//CACHE_TTL))
