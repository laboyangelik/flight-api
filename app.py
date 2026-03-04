import os
import json
import urllib.request
import urllib.parse
from flask import Flask, request, jsonify

app = Flask(__name__)


def search_flights(origin, destination, depart_date, return_date, adults, sort_by=2, include_airlines=None):
    params = {
        "engine":        "google_flights",
        "departure_id":  origin,
        "arrival_id":    destination,
        "outbound_date": depart_date,
        "adults":        str(adults),
        "currency":      "USD",
        "sort_by":       str(sort_by),
        "hl":            "en",
        "api_key":       os.environ.get("SERPAPI_KEY", ""),
    }
    if return_date:
        params["return_date"] = return_date
    if include_airlines:
        params["include_airlines"] = include_airlines

    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=15) as res:
        return json.loads(res.read())


@app.route("/")
def search():
    origin      = request.args.get("origin",      "").strip().upper()
    destination = request.args.get("destination", "").strip().upper()
    depart_date = request.args.get("depart_date", "").strip()
    return_date = request.args.get("return_date", "").strip() or None
    adults      = int(request.args.get("adults", 1))
    sort_by     = int(request.args.get("sort_by", 2))
    include_airlines = request.args.get("include_airlines")

    if not origin or not destination or not depart_date:
        return jsonify({"error": "origin, destination, and depart_date are required"}), 400

    try:
        data = search_flights(origin, destination, depart_date, return_date, adults, sort_by, include_airlines)
        flights = []
        for f in data.get("best_flights", []) + data.get("other_flights", []):
            flights.append({
                "price":     f.get("price"),
                "airline":   f.get("flights", [{}])[0].get("airline"),
                "duration":  f.get("total_duration"),
                "stops":     len(f.get("layovers", [])),
                "departure": f.get("flights", [{}])[0].get("departure_airport", {}).get("time"),
                "arrival":   f.get("flights", [{}])[-1].get("arrival_airport", {}).get("time"),
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
