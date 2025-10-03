# gis_app/views.py

import json
import requests
from math import isnan
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db import connections


# ===================================================================
# Views
# ===================================================================

@login_required
def map_view(request):
    """Render the main map page."""
    return render(request, 'map.html')


# -------------------------------------------------------------------

def identify_feature(request):
    """Fetch attribute information of a feature using GeoServer GetFeatureInfo."""
    bbox = request.GET.get('BBOX')
    width = request.GET.get('WIDTH')
    height = request.GET.get('HEIGHT')
    x = request.GET.get('X')
    y = request.GET.get('Y')

    geoserver_url = 'http://localhost:8080/geoserver/final_project/wms'

    params = {
        'SERVICE': 'WMS',
        'VERSION': '1.1.1',
        'REQUEST': 'GetFeatureInfo',
        'LAYERS': 'final_project:US_STADIUMS',
        'QUERY_LAYERS': 'final_project:US_STADIUMS',
        'INFO_FORMAT': 'application/json',
        'FEATURE_COUNT': '1',
        'X': x,
        'Y': y,
        'SRS': 'EPSG:4326',
        'WIDTH': width,
        'HEIGHT': height,
        'BBOX': bbox,
    }

    try:
        response = requests.get(geoserver_url, params=params, timeout=10)
        response.raise_for_status()
        return JsonResponse(response.json())
    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f'Could not connect to GeoServer: {str(e)}'}, status=502)





# -------------------------------------------------------------------

def get_state_statistics(request):
    """Count stadiums inside a given state using spatial query."""
    state_name = request.GET.get('state_name', '')
    if not state_name:
        return JsonResponse({'error': 'State name not provided'}, status=400)

    with connections['oracle'].cursor() as cursor:
        sql_query = """
            SELECT COUNT(DISTINCT s.OGR_FID)
            FROM US_STADIUMS s, US_STATES t
            WHERE t.NAME = :state_name
            AND SDO_CONTAINS(t.ORA_GEOMETRY, s.ORA_GEOMETRY) = 'TRUE'
        """
        params = {'state_name': state_name}
        cursor.execute(sql_query, params)
        count = cursor.fetchone()[0]

    return JsonResponse({
        'state_name': state_name,
        'stadium_count': count
    })


# -------------------------------------------------------------------

@require_POST
def create_stadium(request):
    """Insert a new stadium into the database."""
    try:
        data = json.loads(request.body.decode('utf-8'))

        name = data.get('name')
        city = data.get('city')
        state = data.get('state')
        lat = data.get('lat')
        lng = data.get('lng')

        # بررسی اولیه
        if not all([name, city, state, lat, lng]):
            return JsonResponse({'status': 'error', 'message': 'Missing required fields.'}, status=400)

        # تبدیل به عدد
        try:
            lat = float(lat)
            lng = float(lng)
        except ValueError:
            return JsonResponse({'status': 'error', 'message': 'Invalid coordinates.'}, status=400)

       
        SRID = 8192

        with connections['oracle'].cursor() as cursor:
            # گرفتن آخرین ID
            cursor.execute("SELECT COALESCE(MAX(OGR_FID), 0) FROM US_STADIUMS")
            max_id = cursor.fetchone()[0] or 0
            new_id = max_id + 1

            # دستور INSERT
            sql_insert = f"""
                INSERT INTO US_STADIUMS 
                (OGR_FID, NAME, CITY, STATE, STATUS_COD, ORA_GEOMETRY) 
                VALUES (
                    :new_id, 
                    :name, 
                    :city, 
                    :state, 
                    'Open', 
                    SDO_GEOMETRY(
                        2001, {SRID}, SDO_POINT_TYPE(:lng, :lat, NULL), NULL, NULL
                    )
                )
            """
            params = {
                'new_id': new_id,
                'name': name,
                'city': city,
                'state': state,
                'lng': lng,
                'lat': lat
            }

            cursor.execute(sql_insert, params)
            connections['oracle'].commit()

        return JsonResponse({'status': 'success', 'message': 'New stadium successfully saved.'})

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON.'}, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()  # چاپ کامل خطا در لاگ سرور
        return JsonResponse({'status': 'error', 'message': f'Oracle error: {str(e)}'}, status=500)


# -------------------------------------------------------------------

def all_states_statistics(request):
    """Compute stadium count for all states."""
    with connections['oracle'].cursor() as cursor:
        sql_query = """
            SELECT t.NAME as state_name, COUNT(DISTINCT s.OGR_FID) as stadium_count
            FROM US_STATES t
            LEFT JOIN US_STADIUMS s
            ON SDO_CONTAINS(t.ORA_GEOMETRY, s.ORA_GEOMETRY) = 'TRUE'
            GROUP BY t.NAME
        """
        cursor.execute(sql_query)
        results = cursor.fetchall()

    stats = {row[0]: row[1] for row in results}
    return JsonResponse(stats)

# ------------------------------------------------------------------

def nearest_stadium(request):
    """Find the nearest stadium to a given lat/lng point."""
    try:
        lat = float(request.GET.get('lat'))
        lng = float(request.GET.get('lng'))
    except (TypeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'lat/lng required'}, status=400)

    # ⚠️ Adjust SRID according to your data (e.g., if stored as SRID=8192, update this)
    srid = 4326

    sql = f"""
        SELECT * FROM (
            SELECT s.NAME,
                   s.CITY,
                   s.STATE,
                   s.ORA_GEOMETRY.SDO_POINT.Y AS LAT,
                   s.ORA_GEOMETRY.SDO_POINT.X AS LNG,
                   SDO_NN_DISTANCE(1) AS DIST_KM
            FROM US_STADIUMS s
            WHERE SDO_NN(
                s.ORA_GEOMETRY,
                SDO_GEOMETRY(2001, {srid}, SDO_POINT_TYPE(:lng, :lat, NULL), NULL, NULL),
                'sdo_num_res=1 unit=KM',
                1
            ) = 'TRUE'
            ORDER BY SDO_NN_DISTANCE(1)
        ) WHERE ROWNUM = 1
    """

    with connections['oracle'].cursor() as cur:
        cur.execute(sql, {'lng': lng, 'lat': lat})
        row = cur.fetchone()

    if not row:
        return JsonResponse({'status': 'error', 'message': 'No stadium found'}, status=404)

    name, city, state, lat0, lng0, dist_km = row
    return JsonResponse({
        'status': 'ok',
        'query_point': {'lat': lat, 'lng': lng},
        'stadium': {
            'name': name,
            'city': city,
            'state': state,
            'lat': float(lat0) if lat0 else None,
            'lng': float(lng0) if lng0 else None,
        },
        'distance_km': float(dist_km)
    })

def search(request):
    """Search stadiums or states by name."""
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse([], safe=False)

    results = []

    with connections['oracle'].cursor() as cursor:
        # 1) Stadiums
        sql_stadiums = """
            SELECT 
                t.NAME, t.CITY, t.STATE,
                t.ORA_GEOMETRY.SDO_POINT.Y AS LATITUDE,
                t.ORA_GEOMETRY.SDO_POINT.X AS LONGITUDE,
                'stadium' AS TYPE
            FROM US_STADIUMS t
            WHERE UPPER(t.NAME) LIKE UPPER(:query)
               OR UPPER(t.CITY) LIKE UPPER(:query)
               OR UPPER(t.STATE) LIKE UPPER(:query)
        """
        cursor.execute(sql_stadiums, {'query': f'%{query}%'})
        cols = [col[0] for col in cursor.description]
        for row in cursor.fetchall():
            results.append(dict(zip(cols, row)))

        # 2) States
        sql_states = """
            SELECT 
                t.NAME, 
                t.STUSPS,
                SDO_GEOM.SDO_CENTROID(t.ORA_GEOMETRY, 0.005).SDO_POINT.Y AS LATITUDE,
                SDO_GEOM.SDO_CENTROID(t.ORA_GEOMETRY, 0.005).SDO_POINT.X AS LONGITUDE,
                'state' AS TYPE
            FROM US_STATES t
            WHERE UPPER(t.NAME) LIKE UPPER(:query)
               OR UPPER(t.STUSPS) LIKE UPPER(:query)
        """
        cursor.execute(sql_states, {'query': f'%{query}%'})
        cols = [col[0] for col in cursor.description]
        for row in cursor.fetchall():
            results.append(dict(zip(cols, row)))

    return JsonResponse(results, safe=False)



# gis_app/views.py
from django.shortcuts import render
from django.http import JsonResponse
from django.db import connections
import json

ORACLE_ALIAS = 'oracle'
SCHEMA       = 'SYSTEM'

def update_stadium(request, objectid):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid method."}, status=405)

    try:
        data = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"status": "error", "message": "Invalid JSON."}, status=400)

    name  = data.get("name")
    city  = data.get("city")
    state = data.get("state")

    if not all([name, city, state]):
        return JsonResponse({"status": "error", "message": "Missing fields."}, status=400)

    try:
        with connections[ORACLE_ALIAS].cursor() as cursor:
            cursor.execute(f"""
                UPDATE {SCHEMA}.US_STADIUMS
                   SET NAME = :name, CITY = :city, STATE = :state
                 WHERE OBJECTID = :oid
            """, {"name": name, "city": city, "state": state, "oid": objectid})

        # ✅ این خط مهمه (بدونش تغییر اعمال نمیشه)
        connections[ORACLE_ALIAS].commit()

        return JsonResponse({"status": "success", "message": "Stadium updated."})

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
