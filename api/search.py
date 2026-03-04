import json
import os
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler


def search_flights(origin, destination, depart_date, return_date, adults, sort_by=2, include_airlines=None):
    params = {
        "engine":         "google_flights",
        "departure_id":   origin,
        "arrival_id":     destination,
        "outbound_date":  depart_date,
        "adults":         str(adults),
        "currency":       "USD",
        "sort_by":        str(sort_by),
        "hl":             "en",
        "api_key":        os.environ.get("SERPAPI_KEY", ""),
    }
    if return_date:
        params["return_date"] = return_date
    if include_airlines:
        params["include_airlines"] = include_airlines

    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)

    with urllib.request.urlopen(req, timeout=15) as res:
        return json.loads(res.read())


def parse_flight(f):
    return {
        "price":    f.get("price"),
        "airline":  f.get("flights", [{}])[0].get("airline"),
        "duration": f.get("total_duration"),
        "stops":    len(f.get("layovers", [])),
        "departure": f.get("flights", [{}])[0].get("departure_airport", {}).get("time"),
        "arrival":   f.get("flights", [{}])[-1].get("arrival_airport", {}).get("time"),
        "is_best":   True,
    }


class handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        params      = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        origin      = params.get("origin",      [""])[0].strip().upper()
        destination = params.get("destination", [""])[0].strip().upper()
        depart_date = params.get("depart_date", [""])[0].strip()
        return_date = (params.get("return_date", [None])[0] or "").strip() or None
        adults      = int(params.get("adults",  [1])[0])
        sort_by          = int(params.get("sort_by", [2])[0])
        include_airlines = params.get("include_airlines", [None])[0]

        if not origin or not destination or not depart_date:
            self.send_json(400, {"error": "origin, destination, and depart_date are required"})
            return

        try:
            data    = search_flights(origin, destination, depart_date, return_date, adults, sort_by, include_airlines)
            flights = [parse_flight(f) for f in data.get("best_flights", []) + data.get("other_flights", [])]

            self.send_json(200, {
                "origin":      origin,
                "destination": destination,
                "depart_date": depart_date,
                "return_date": return_date,
                "adults":      adults,
                "flights":     flights[:15],
            })

        except Exception as e:
            self.send_json(500, {"error": str(e)})
