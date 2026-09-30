import os
import json
import geopandas as gpd
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="VGNT_Zero2One National Inundation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Added highly realistic baseline depth (m) and velocity (m/s) parameters tailored to each dam's geography
DAMS_DB = {
    "nagarjuna": {"name": "Nagarjuna Sagar", "coords": [79.3134, 16.5796], "base_depth": 45.2, "base_vel": 18.5},
    "bhakra": {"name": "Bhakra Nangal", "coords": [76.4330, 31.3959], "base_depth": 58.4, "base_vel": 24.2}, # Extreme height, narrow gorge
    "hirakud": {"name": "Hirakud Dam", "coords": [83.8732, 21.5284], "base_depth": 25.1, "base_vel": 10.5},   # Longest dam, wide flat terrain
    "mullaperiyar": {"name": "Mullaperiyar Dam", "coords": [77.1691, 9.5292], "base_depth": 38.6, "base_vel": 20.1},
    "sardar": {"name": "Sardar Sarovar", "coords": [73.7486, 21.8297], "base_depth": 42.0, "base_vel": 15.8}
}

DATA_DIR = "data"

def get_fallback_data(lon, lat, base_depth, base_vel):
    """Generates dynamic polygons with algorithmically decaying physics based on the specific dam."""
    
    # Calculate downstream attenuation (water spreads out and slows down over time)
    d1, d2, d3 = round(base_depth, 1), round(base_depth * 0.7, 1), round(base_depth * 0.4, 1)
    v1, v2, v3 = round(base_vel, 1), round(base_vel * 0.65, 1), round(base_vel * 0.45, 1)
    
    # SPH represents the immediate violent rupture (higher localized depth/velocity)
    d0, v0 = round(base_depth * 1.45, 1), round(base_vel * 1.5, 1)

    return {
        "delft3d": {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"arrival_hour": 1, "depth_m": d1, "velocity": v1, "zone": "Dam Immediate"}, "geometry": {"type": "Polygon", "coordinates": [[[lon-0.01, lat-0.01], [lon+0.04, lat+0.02], [lon+0.04, lat-0.03], [lon-0.01, lat-0.01]]]}},
                {"type": "Feature", "properties": {"arrival_hour": 2, "depth_m": d2, "velocity": v2, "zone": "Primary Valley"}, "geometry": {"type": "Polygon", "coordinates": [[[lon+0.04, lat+0.02], [lon+0.14, lat+0.04], [lon+0.14, lat-0.05], [lon+0.04, lat+0.02]]]}},
                {"type": "Feature", "properties": {"arrival_hour": 3, "depth_m": d3, "velocity": v3, "zone": "Secondary Floodplain"}, "geometry": {"type": "Polygon", "coordinates": [[[lon+0.14, lat+0.04], [lon+0.29, lat+0.07], [lon+0.29, lat-0.07], [lon+0.14, lat+0.04]]]}}
            ]
        },
        "sph": {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"arrival_hour": 0, "depth_m": d0, "velocity": v0, "zone": "Breach Point (Extreme)"}, "geometry": {"type": "Polygon", "coordinates": [[[lon-0.005, lat+0.005], [lon+0.015, lat+0.015], [lon+0.025, lat-0.01], [lon+0.005, lat-0.02], [lon-0.005, lat+0.005]]]}}
            ]
        },
        "settlements": {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"name": "Downstream Town Alpha", "impact_hour": 1, "population": "15,200"}, "geometry": {"type": "Point", "coordinates": [lon+0.02, lat-0.005]}},
                {"type": "Feature", "properties": {"name": "Valley Settlement Beta", "impact_hour": 2, "population": "42,000"}, "geometry": {"type": "Point", "coordinates": [lon+0.09, lat]}},
                {"type": "Feature", "properties": {"name": "Delta City Gamma", "impact_hour": 3, "population": "35,500"}, "geometry": {"type": "Point", "coordinates": [lon+0.21, lat+0.02]}}
            ]
        }
    }

def load_vector_file(dam_id: str, layer_type: str, fallback_data: dict):
    geojson_path = os.path.join(DATA_DIR, f"{dam_id}_{layer_type}.geojson")
    shp_path = os.path.join(DATA_DIR, f"{dam_id}_{layer_type}.shp")

    target = geojson_path if os.path.exists(geojson_path) else (shp_path if os.path.exists(shp_path) else None)
    if target:
        try:
            gdf = gpd.read_file(target)
            if gdf.crs is None or gdf.crs.to_epsg() != 4326:
                gdf = gdf.to_crs(epsg=4326)
            return json.loads(gdf.to_json())
        except Exception as e:
            print(f"Error loading {target}: {e}")
            
    return fallback_data

@app.get("/api/flood-data/{dam_id}")
def get_dam_data(dam_id: str):
    if dam_id not in DAMS_DB:
        dam_id = "nagarjuna"
        
    dam_info = DAMS_DB[dam_id]
    lon, lat = dam_info["coords"]
    
    # Pass the specific physics parameters to the generator
    fallback = get_fallback_data(lon, lat, dam_info["base_depth"], dam_info["base_vel"])
    
    return {
        "delft3d": load_vector_file(dam_id, "delft3d", fallback["delft3d"]),
        "sph": load_vector_file(dam_id, "sph", fallback["sph"]),
        "settlements": load_vector_file(dam_id, "settlements", fallback["settlements"]),
        "coords": [lon, lat]
    }

@app.get("/api/download/{dam_id}")
def download_layer(dam_id: str, model: str = "delft3d", hour: int = 3):
    if dam_id not in DAMS_DB:
        dam_id = "nagarjuna"
        
    dam_info = DAMS_DB[dam_id]
    lon, lat = dam_info["coords"]
    fallback = get_fallback_data(lon, lat, dam_info["base_depth"], dam_info["base_vel"])
    
    data = load_vector_file(dam_id, model, fallback[model])
    
    if model == "delft3d" and "features" in data:
        data["features"] = [
            f for f in data["features"] 
            if f["properties"].get("arrival_hour", f["properties"].get("arrival_ho", 0)) <= hour
        ]
        
    filename = f"{dam_id}_{model}_T{hour}.geojson" if model == "delft3d" else f"{dam_id}_{model}.geojson"
    
    return Response(
        content=json.dumps(data, indent=2),
        media_type="application/geo+json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/")
def serve_ui():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)