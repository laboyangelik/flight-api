import json
import os
import urllib.request
import urllib.parse
from flask import Flask, request, jsonify

app = Flask(__name__)

RAPIDAPI_KEY  = os.environ.get("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "sky-scrapper.p.rapidapi.com"

_airport_cache = {}


def sky_request(path, params):
    url = f"https://{RAPIDAPI_HOST}{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key":  RAPIDAPI_KEY,
    })
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.loads(res.read())


def get_airport(iata):
    if iata in _airport_cache:
        return _airport_cache[iata]

    data   = sky_request("/api/v1/flights/searchAirport", {"query": iata, "locale": "en-US"})
    places = data.get("data", [])

    for place in places:
        if place.get("skyId", "").upper() == iata.upper():
            result = (place["skyId"], str(place["entityId"]))
            _airport_cache[iata] = result
            return result

    if places:
        result = (places[0]["skyId"], str(places[0]["entityId"]))
        _airport_cache[iata] = result
        return result

    raise ValueError(f"Airport not found: {iata}")


@app.route("/")
def search():
    origin      = request.args.get("origin",      "").strip().upper()
    destination = request.args.get("destination", "").strip().upper()
    depart_date = request.args.get("depart_date", "").strip()
    return_date = request.args.get("return_date", "").strip() or None
    adults      = int(request.args.get("adults", 1))
    sort_by     = request.args.get("sort_by", "best").strip()

    if not origin or not destination or not depart_date:
        return jsonify({"error": "origin, destination, and depart_date are required"}), 400

    try:
        origin_sky_id, origin_entity_id = get_airport(origin)
        dest_sky_id,   dest_entity_id   = get_airport(destination)

        params = {
            "originSkyId":         origin_sky_id,
            "destinationSkyId":    dest_sky_id,
            "originEntityId":      origin_entity_id,
            "destinationEntityId": dest_entity_id,
            "date":                depart_date,
            "cabinClass":          "economy",
            "adults":              str(adults),
            "sortBy":              sort_by,
            "currency":            "USD",
            "market":              "en-US",
            "countryCode":         "US",
        }
        if return_date:
            params["returnDate"] = return_date

        data  = sky_request("/api/v2/flights/searchFlights", params)
        itins = data.get("data", {}).get("itineraries", [])

        flights = []
        for itin in itins:
            legs = itin.get("legs", [])
            if not legs:
                continue
            leg       = legs[0]
            marketing = leg.get("carriers", {}).get("marketing", [{}])
            airline   = marketing[0].get("name", "") if marketing else ""
            segments  = leg.get("segments", [])
            departure = segments[0].get("departure", "")  if segments else leg.get("departure", "")
            arrival   = segments[-1].get("arrival",   "")  if segments else leg.get("arrival",   "")
            price     = itin.get("price", {}).get("raw")

            flights.append({
                "price":     price,
                "airline":   airline,
                "duration":  leg.get("durationInMinutes"),
                "stops":     leg.get("stopCount", 0),
                "departure": departure,
                "arrival":   arrival,
                "is_best":   True,
            })

        return jsonify({
            "origin":      origin,
            "destination": destination,
            "depart_date": depart_date,
            "return_date": return_date,
            "adults":      adults,
            "flights":     flights[:15],
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
