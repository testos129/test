from urllib.parse import unquote
import requests
import re

from services.file_io import load_yaml
from services.logging_setup import get_logger
functionalities_switch = load_yaml('components/functionalities_switch.yaml')
ADDRESS_DEFAULT_PARIS = functionalities_switch.get('ADDRESS_DEFAULT_PARIS', True)

logger = get_logger('default')


def get_coords_from_address(address: str):

    """
    Récupère les coordonnées géographiques (latitude et longitude) d'une adresse donnée
    en utilisant l'API data gouv

     Args:
        address (str): L'adresse à géocoder, encodée ou non URL.

    Returns:
        tuple:
            - (True, (lat, lng)) si une adresse valide est trouvée à Paris.
            - (False, "no_addr_found") si aucune adresse valide n'a été trouvée.
            - (False, "error_geocoding", exception) si une erreur se produit lors du géocodage.
    """

    address = unquote(address)
    try:
        geo_resp = requests.get(
           "https://api-adresse.data.gouv.fr/search/",
           params={"q": address},
            headers={"User-Agent": "AppPrototype"}
        )

        geo_data = geo_resp.json()

        # Vérification supplémentaire pour Paris
        pattern = re.compile(r"^(75(?:0[0-9]{2}|1[0-9]{2}))$")  # match 75xxx avex xxx entre 001 et 020 et entre 116 et 118

        if ADDRESS_DEFAULT_PARIS:
            geo_data_paris = [data for data in geo_data['features'] if bool(pattern.match(data['properties']['postcode']))]
        
            if geo_data_paris:
                best = geo_data_paris[0]
            else:
                best = geo_data['features'][0]
        
        else:
             best = geo_data['features'][0]

        lat, lng = float(best['geometry']['coordinates'][1]), float(best['geometry']['coordinates'][0])

        return (True, (lat, lng))
    
    except Exception as e:
        logger.warning(f"Error during geocoding for address: {address}: {e}")
        return (False, "error_geocoding", e)


# NOT USED
def get_coords_from_address_nominatim(address: str):

    """
    Récupère les coordonnées géographiques (latitude et longitude) d'une adresse donnée
    en utilisant l'API de géocodage Nominatim (OpenStreetMap).

    La fonction effectue une recherche initiale limitée à 3 résultats et filtre
    pour ne garder que ceux situés à Paris. Si aucun résultat parisien n'est trouvé,
    elle effectue une seconde recherche avec une limite de 10 résultats.

    Args:
        address (str): L'adresse à géocoder, encodée ou non URL.

    Returns:
        tuple:
            - (True, (lat, lng)) si une adresse valide est trouvée à Paris.
            - (False, "no_addr_found") si aucune adresse valide n'a été trouvée.
            - (False, "error_geocoding", exception) si une erreur se produit lors du géocodage.
    """

    address = unquote(address)
    try:
        geo_resp = requests.get(
            "https://nominatim.openstreetmap.org/search",   # Recherche des coordonnées pour cette adresse sur openstreetmap
            params={"q": address, 
                    "format": "json", 
                    "limit": 3,
                    "addressdetails": 1
                    },
            headers={"User-Agent": "AppPrototype"}
        )
        geo_data = geo_resp.json()
        if geo_data:

            paris_results = [
            d for d in geo_data
            if "address" in d and (
                d["address"].get("city") == "Paris" or
                d["address"].get("county") == "Paris" or
                "Paris" in d.get("display_name", "")
                )
            ]

            if not paris_results:                        
                # Recherche avec limite de 10 pour trouver plus de résultats
                geo_resp_2 = requests.get(
                    "https://nominatim.openstreetmap.org/search",   # Recherche des coordonnées pour cette adresse sur openstreetmap
                    params={"q": address, 
                            "format": "json", 
                            "limit": 10,
                            "addressdetails": 1
                            },
                    headers={"User-Agent": "AppPrototype"}
                )
                geo_data_2 = geo_resp_2.json()

                if geo_data_2:

                    paris_results_2 = [
                    d for d in geo_data_2
                    if "address" in d and (
                        d["address"].get("city") == "Paris" or
                        d["address"].get("county") == "Paris" or
                        "Paris" in d.get("display_name", "")
                        )
                    ]

                    if not paris_results_2:
                        best = geo_data_2[0]
                    else:
                        best = paris_results_2[0]       

                else:
                    return (False, "no_addr_found")
             
            else:
                best = paris_results[0]

            lat, lng = float(best["lat"]), float(best["lon"])

            return (True, (lat, lng))

        else:
            return (False, "no_addr_found")
        
    except Exception as e:
        return (False, "error_geocoding", e)