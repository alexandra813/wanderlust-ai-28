from flask import Flask, render_template, request
import requests
import math
import os

app = Flask(__name__)

MONTHS = ["January", "February", "March", "April", "May", "June", 
          "July", "August", "September", "October", "November", "December"]

def get_attractions(lat, lon, city_name=""):
    """Fetch nearby attractions from Wikipedia API with descriptions"""
    try:
        # 1. Search for places nearby
        url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "query",
            "list": "geosearch",
            "gscoord": f"{lat}|{lon}",
            "gsradius": 10000, # 10km radius
            "gslimit": 10,
            "format": "json"
        }
        headers = {'User-Agent': 'TravelTimeApp/1.0 (contact@example.com)'}
        response = requests.get(url, params=search_params, headers=headers)
        data = response.json()
        
        places = data.get('query', {}).get('geosearch', [])
        
        # FALLBACK: If no places found via Geo (e.g., Monaco might be tricky or API limit), 
        # search for the City Name itself as a page to at least show something.
        if not places and city_name:
             text_params = {
                "action": "query",
                "list": "search",
                "srsearch": f"{city_name} tourist attraction",
                "srlimit": 5,
                "format": "json"
             }
             text_resp = requests.get(url, params=text_params, headers=headers)
             places = text_resp.json().get('query', {}).get('search', [])
             # Normalize keys (geosearch has 'dist', search doesn't)
             for p in places:
                 p['dist'] = 0 # Unknown distance

        if not places:
            return [{"title": f"Explore {city_name}", "dist": 0, "description": "We couldn't find specific geotagged attractions, but this city is definitely worth exploring!", "ticket_link": f"https://www.google.com/search?q=things+to+do+in+{city_name}", "ticket_text": "Search Google", "is_free": True}]
            
        # 2. Get details for these places (extracts/descriptions)
        pageids = "|".join(str(p['pageid']) for p in places)
        details_params = {
            "action": "query",
            "prop": "extracts|info",
            "pageids": pageids,
            "exintro": True,
            "explaintext": True,
            "inprop": "url",
            "exchars": 600, 
            "format": "json"
        }
        details_resp = requests.get(url, params=details_params, headers=headers)
        details_data = details_resp.json().get('query', {}).get('pages', {})
        
        results = []
        for p in places:
            pid = str(p['pageid'])
            details = details_data.get(pid, {})
            title = p['title']
            
            description = details.get('extract', 'No description available.')
            
            # Ticket Logic Heuristic
            lower_desc = description.lower()
            if any(x in lower_desc for x in ['public park', 'free admission', 'no entry fee', 'open to the public', 'public square']):
                is_free = True
                ticket_text = "Free / Visit Info"
                ticket_link = f"https://www.google.com/search?q={title.replace(' ', '+')}+visitor+info"
            else:
                is_free = False
                ticket_text = "🎟 Buy Tickets"
                # Ticketmaster/Viator/GetYourGuide search
                ticket_link = f"https://www.google.com/search?q={title.replace(' ', '+')}+official+site+tickets"

            # Ensure strict length
            if len(description) > 600:
                description = description[:600] + '...'

            results.append({
                "title": title,
                "dist": p.get('dist', 0), 
                "lat": p.get('lat'), # Wiki API returns these
                "lon": p.get('lon'),
                "description": description,
                "wiki_url": details.get('fullurl', '#'),
                "ticket_link": ticket_link,
                "ticket_text": ticket_text,
                "is_free": is_free
            })
            
        return results
    except Exception as e:
        print(f"Error fetching attractions: {e}")
        return [{"title": "Could not fetch local attractions.", "dist": 0, "description": f"Error: {str(e)}", "ticket_link": "#", "ticket_text": "Error"}]

def get_accommodation_links(city_name):
    """Generate search links for hotels"""
    city_encoded = city_name.replace(' ', '+')
    return {
        "booking": f"https://www.booking.com/searchresults.html?ss={city_encoded}",
        "airbnb": f"https://www.airbnb.com/s/{city_encoded}/homes",
        "google_hotels": f"https://www.google.com/travel/hotels?q={city_encoded}"
    }

def generate_context_tips(lat, lon, best_month, scores=None):
    """Generate tips based on season, location, crowds, and cost"""
    # Defensive default if scores not passed
    if scores is None:
        scores = {'crowd': 50, 'cost': 50}

    tips = []
    
    # 1. Climate Zone Logic
    if abs(lat) < 23.5:
        tips.append("Tropical climate: Expect humidity and sudden showers. Pack breathable fabrics.")
        tips.append("Mosquito repellent is a must for this region.")
    elif abs(lat) > 60:
        tips.append("High latitude: Days can be very long or very short depending on season.")
        tips.append("Pack thermal layers, even if it looks sunny.")
    elif 23.5 <= abs(lat) < 35:
        tips.append("Subtropical/Desert zone: High UV index. Sunscreen and hat are essential.")
        
    # 2. Seasonality Logic
    is_northern = lat > 0
    month_idx = MONTHS.index(best_month)
    
    is_winter = False
    is_summer = False
    
    if is_northern:
        if month_idx in [11, 0, 1]: is_winter = True
        if month_idx in [5, 6, 7]: is_summer = True
    else:
        if month_idx in [5, 6, 7]: is_winter = True
        if month_idx in [11, 0, 1]: is_summer = True
        
    if is_winter:
        tips.append("Winter season: Pack a warm coat and check if outdoor attractions close early.")
    elif is_summer:
        tips.append("Summer season: Stay hydrated and plan indoor activities for the hottest part of the day.")
    
    # 3. Crowd Logic (Score < 50 means crowded/bad)
    if scores['crowd'] < 40:
        tips.append("It will be busy! Book tickets for major attractions at least 2 weeks in advance.")
        tips.append("Visit popular spots early in the morning (before 9 AM) to avoid crowds.")
    elif scores['crowd'] > 80:
        tips.append("Great choice! It's quiet season, so you'll have the streets to yourself.")

    # 4. Budget Logic (Score < 50 means expensive/bad)
    if scores['cost'] < 40:
        tips.append("This is a pricier destination. Consider a city pass for transport and museums.")
    elif scores['cost'] > 80:
        tips.append("Destination offers great value right now. perfect time for fine dining.")

    # 5. Zone-Specific Tips
    # Europe: Lat 35-70, Lon -10 to 40
    if 35 <= lat <= 70 and -10 <= lon <= 40:
        tips.append("Europe tip: Many museums are closed on Mondays. Check schedules ahead.")
        tips.append("Europe tip: Public transport is excellent, download the local metro app.")

    # Asia: Lat 10-55, Lon 60-150
    elif 10 <= lat <= 55 and 60 <= lon <= 150:
        tips.append("Asia tip: Carry cash (local currency) for street food and small vendors.")
        tips.append("Asia tip: Apps like Grab or Gojek are essential for transport in SE Asia.")

    # North America: Lat 25-70, Lon -170 to -50
    elif 25 <= lat <= 70 and -170 <= lon <= -50:
        tips.append("North America tip: Tipping 15-20% is standard in restaurants.")
        
    # South America: Lat -55 to 15, Lon -85 to -35
    elif -55 <= lat <= 15 and -85 <= lon <= -35:
        tips.append("South America tip: Learn a few basic Spanish/Portuguese phrases.")
        tips.append("South America tip: Uber works well in major cities, but verify license plates.")

    # Africa: Lat -35 to 37, Lon -20 to 55
    elif -35 <= lat <= 37 and -20 <= lon <= 55:
        tips.append("Africa tip: Drinking bottled water is recommended in many regions.")

    # Oceania: Lat -50 to -10, Lon 110 to 180
    elif -50 <= lat <= -10 and 110 <= lon <= 180:
         tips.append("Oceania tip: Sun is very strong; use SPF 50+ sunscreen.")

    # Ensure we always have some tips
    if len(tips) < 2:
        tips.append("Download offline maps and check visa requirements.")
        tips.append("Respect local customs and dress appropriately for religious sites.")
        
    return tips[:5] # Limit to top 5 tips

def analyze_dynamic(lat, lon):
    """
    Generate scores based on Latitude (Climate approximation).
    Very simplified model:
    - Northern Hemisphere: Summer (Jun-Aug) is warm, Winter (Dec-Feb) is cold.
    - Southern Hemisphere: Summer (Dec-Feb) is warm, Winter (Jun-Aug) is cold.
    - Tropics (-23 to 23): Warm all year, wet/dry seasons (assume Winter is drier/better).
    """
    try:
        lat = float(lat)
    except:
        lat = 0.0

    scores = []
    
    # Weights
    W_WEATHER = 0.4
    W_CROWD = 0.3
    W_COST = 0.3

    is_northern = lat > 0
    is_tropics = abs(lat) < 23.5

    for i in range(12):
        month_idx = i # 0 = Jan
        
        # 1. WEATHER SCORE (1-10)
        # Simplified: People generally like "Warm but not hot".
        if is_tropics:
            # Tropics: Winter months often better (drier). 
            # North Tropics: Jan (0) is good. South Tropics: July (6) is good.
            # Let's simple sine wave it: Peak at "Winter".
            if lat > 0: # North Tropics
                # Peak Jan(0), Dip July(6)
                dist_from_jan = min(abs(month_idx - 0), abs(month_idx - 12))
                weather_val = 9 - (dist_from_jan * 0.5) 
            else: # South Tropics
                # Peak July(6)
                dist_from_july = abs(month_idx - 6)
                weather_val = 9 - (dist_from_july * 0.5)
        elif is_northern:
            # North Temperate: Summer (July) is hot/good, Winter (Jan) is cold/bad.
            # Let's say May/Sep are Peak (8-9), July is good (8), Jan is bad (2).
            # Simple interaction:
            # Jan(0) -> 2
            # July(6) -> 9
            dist_from_july = abs(month_idx - 6)
            weather_val = 10 - dist_from_july
        else:
            # South Temperate: Jan (Summer) is good. July (Winter) is bad.
            dist_from_jan = min(abs(month_idx - 0), abs(month_idx - 12))
            weather_val = 10 - dist_from_jan
            
        weather_score = max(1, min(10, weather_val))

        # 2. CROWD SCORE (1-10, 10=Packed)
        # People travel in Summer (School holidays).
        # North Summer: Jun-Aug. South Summer: Dec-Jan.
        if is_northern:
            if 5 <= month_idx <= 7: # Jun-Aug
                crowd_val = 9
            elif month_idx == 11 or month_idx == 0: # Dec/Jan (Holidays)
                crowd_val = 7
            else:
                crowd_val = 4
        else:
            if month_idx == 11 or month_idx <= 1: # Dec-Feb
                crowd_val = 9
            else:
                crowd_val = 4
                
        # Invert for score (Low crowds = good)
        crowd_score_inv = 11 - crowd_val

        # 3. COST SCORE (1-10, 10=Expensive)
        # Correlates with Crowds usually.
        cost_val = crowd_val 
        cost_score_inv = 11 - cost_val

        # Weighted Total
        total_score = (weather_score * W_WEATHER) + (crowd_score_inv * W_CROWD) + (cost_score_inv * W_COST)
        scores.append(total_score)

    best_month_index = scores.index(max(scores))
    
    # Calculate Display Stats
    if is_northern:
        if 5 <= best_month_index <= 7: 
             weather_raw = 90
             crowd_raw = 30 # Crowded
             cost_raw = 40
        else:
             weather_raw = 70
             crowd_raw = 80 # Empty
             cost_raw = 80
            
    else:
         # Generic stats for display based on the calculated score
         weather_raw = int(scores[best_month_index] * 10) # rough
         crowd_raw = 70
         cost_raw = 70

    return {
        "best_month": MONTHS[best_month_index],
        "scores": {
            "weather": int(weather_raw),
            "crowd": int(crowd_raw),
            "cost": int(cost_raw)
        },
        "lat": round(lat, 2),
        "lon": round(float(lon), 2)
    }

@app.route('/', methods=['GET', 'POST'])
def home():
    result = None
    selected_city = None
    
    if request.method == 'POST':
        selected_city = request.form.get('city', 'Unknown Location')
        lat = request.form.get('lat')
        lon = request.form.get('lon')
        
        if lat and lon:
            analysis = analyze_dynamic(lat, lon)
            attractions = get_attractions(lat, lon, selected_city)
            
            result = {
                **analysis,
                "attractions": attractions,
                "hotels": get_accommodation_links(selected_city),
                "tips": generate_context_tips(analysis['lat'], analysis['lon'], analysis['best_month'], analysis['scores'])
            }
            
    return render_template('travel_index.html', 
                         result=result, 
                         selected_city=selected_city,
                         cities=[]) # Empty list as we use map now

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)