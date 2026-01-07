from nicegui import ui, app
from fastapi import Request

from services.users import update_user_coordinates


@app.post('/api/update_position')
async def update_position(request: Request):

    data = await request.json()
    user_id = data.get("user_id")
    lat = data.get("lat")
    lng = data.get("lng")

    if not user_id or lat is None or lng is None:
        return {"success": False, "error": "Missing data"}

    update_user_coordinates(user_id, lat, lng)

    return {"success": True}


def start_geolocation_tracking(user_id: int):

    ui.run_javascript(f"""
        if (window._geoTrackerStarted) return;
        window._geoTrackerStarted = true;

        async function sendPosition() {{
            if (!navigator.geolocation) {{
                console.log("Geolocation not supported");
                return;
            }}

            navigator.geolocation.getCurrentPosition(async (pos) => {{
                const lat = pos.coords.latitude;
                const lng = pos.coords.longitude;

                console.log("Position envoyée:", lat, lng);

                await fetch('/api/update_position', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        user_id: {user_id},
                        lat: lat,
                        lng: lng
                    }})
                }}).catch(err => console.error("Erreur géoloc:", err));
            }}, 
            (err) => {{
                console.warn("Erreur GPS:", err);
            }},
            {{
                enableHighAccuracy: true,
                maximumAge: 5000
            }});
        }}

        // Lancer immédiatement
        sendPosition();

        // Puis toutes les 10 secondes
        setInterval(sendPosition, 10000);
    """)
