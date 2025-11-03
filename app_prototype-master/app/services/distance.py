import math

def haversine_dist(lat1: float, lon1: float, lat2: float, lon2: float):

    """Retourne la distance à vol d'oiseau en kilomètres"""

    R = 6371  # Rayon de la Terre en km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2

    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def optimize_route(start_lat, start_lng, pharmacies, end_lat=None, end_lng=None):

    """Retourne une liste ordonnée de pharmacies pour minimiser la distance totale parcourue"""

    unvisited = pharmacies[:]
    ordered = []
    current = {"lat": start_lat, "lng": start_lng}

    while unvisited:
        next_ph = min(unvisited, key=lambda ph: haversine_dist(current["lat"], current["lng"], ph["lat"], ph["lng"]))
        ordered.append(next_ph)
        unvisited.remove(next_ph)
        current = next_ph

    if end_lat is not None and end_lng is not None:
        ordered.append({"lat": end_lat, "lng": end_lng, "name": "Destination finale"})

    return ordered