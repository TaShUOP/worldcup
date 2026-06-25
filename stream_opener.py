import requests
import time
import webbrowser
import pyautogui
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

API_URL = "https://api.ppv.to/api/streams"
TARGET_TAG = "fifa world cup"

def open_stream(event_id, name, url):
    print(f"\n[{datetime.now()}] Opening stream for '{name}'...")
    try:
        # Open in default browser natively (avoids all profile lock issues)
        webbrowser.open(url)
        
        # Wait 15 seconds for the player to load
        time.sleep(15)
        
        # Click the center of the screen
        screen_width, screen_height = pyautogui.size()
        pyautogui.click(screen_width / 2, screen_height / 2)
        
        print(f"[{datetime.now()}] Auto-clicked center of screen.")
        print(f"[{datetime.now()}] Successfully opened '{name}'.")
    except Exception as e:
        print(f"[{datetime.now()}] Error opening '{name}': {e}")

def close_stream(event_id, name):
    print(f"\n[{datetime.now()}] Closing stream for '{name}'...")
    try:
        # Use Ctrl+W to close the active tab
        pyautogui.hotkey('ctrl', 'w')
        print(f"[{datetime.now()}] Successfully closed '{name}'.")
    except Exception as e:
        print(f"[{datetime.now()}] Error closing '{name}': {e}")

def fetch_and_schedule_events(scheduler):
    print(f"\n[{datetime.now()}] Fetching events from {API_URL}...")
    try:
        response = requests.get(API_URL)
        response.raise_for_status()
        data = response.json()

        raw_target_events = []
        for category in data.get('streams', []):
            for event in category.get('streams', []):
                tags = []
                if event.get('tag'): tags.append(event['tag'].lower())
                if event.get('category_name'): tags.append(event['category_name'].lower())
                
                # Step 1: Extract all streams matching the target tag (e.g., fifa world cup)
                if TARGET_TAG.lower() in tags:
                    is_fox = False
                    fox_iframe = None
                    
                    # Check the parent stream first
                    if 'FOX' in event.get('source_tag', '').upper():
                        is_fox = True
                        
                    # Check all available substreams for a FOX broadcast
                    for sub in event.get('substreams', []):
                        if 'FOX' in sub.get('source_tag', '').upper():
                            is_fox = True
                            fox_iframe = sub.get('iframe')
                            break # Found a FOX stream, stop searching substreams
                            
                    event['has_fox'] = is_fox
                    # If we found a specific FOX iframe in a substream, overwrite the parent iframe
                    if fox_iframe:
                        event['iframe'] = fox_iframe
                        
                    raw_target_events.append(event)
        
        # Step 2: Handle overlaps (2 streams at the same time)
        events_by_time = {}
        for event in raw_target_events:
            start_ts = event.get('starts_at')
            if not start_ts: continue
            if start_ts not in events_by_time:
                events_by_time[start_ts] = []
            events_by_time[start_ts].append(event)
            
        target_events = []
        for start_ts, concurrent_events in events_by_time.items():
            if len(concurrent_events) > 1:
                # Predict popularity/preference:
                # 1. Prefer streams with 'FOX' (either parent or substream).
                # 2. If tied (both FOX, or neither FOX), pick the one with highest viewers.
                concurrent_events.sort(
                    key=lambda e: (
                        e.get('has_fox', False), 
                        int(e.get('viewers', 0))
                    ), 
                    reverse=True
                )
                winner = concurrent_events[0]
                print(f"[{datetime.now()}] Conflict at {datetime.fromtimestamp(start_ts)}: {len(concurrent_events)} matches.")
                print(f" - Selected: '{winner.get('name')}' (FOX: {winner.get('has_fox', False)}, Viewers: {winner.get('viewers', 0)})")
                target_events.append(winner)
            else:
                target_events.append(concurrent_events[0])

        print(f"[{datetime.now()}] Found {len(target_events)} events matching '{TARGET_TAG}' to schedule.")
        
        now = datetime.now()

        for event in target_events:
            event_id = str(event.get('id', id(event)))
            name = event.get('name', 'Unknown Event')
            start_ts = event.get('starts_at')
            end_ts = event.get('ends_at')
            # Prefer the iframe directly to open the stream
            url = event.get('iframe') or f"https://ppv.to/event/{event.get('uri_name', '')}"

            if not all([start_ts, end_ts, url]):
                continue

            try:
                # fromtimestamp automatically converts the Unix UTC timestamp to your local timezone (IST)
                start_time = datetime.fromtimestamp(start_ts)
                end_time = datetime.fromtimestamp(end_ts)
            except (ValueError, TypeError):
                continue

            open_time = start_time - timedelta(minutes=10)
            close_time = end_time + timedelta(minutes=5)

            # Check if event is entirely in the past
            if close_time < now:
                continue

            # Schedule Open
            if open_time > now:
                scheduler.add_job(
                    open_stream, 
                    'date', 
                    run_date=open_time, 
                    args=[event_id, name, url],
                    id=f"open_{event_id}",
                    replace_existing=True
                )
                print(f" - Scheduled OPEN for '{name}' at {open_time.strftime('%Y-%m-%d %H:%M:%S')} (Local Time)")
            elif start_time < now < end_time:
                # Event is ongoing and not currently opened, open immediately
                print(f" - Event '{name}' is currently ongoing. Opening now.")
                open_stream(event_id, name, url)

            # Schedule Close
            if close_time > now:
                scheduler.add_job(
                    close_stream, 
                    'date', 
                    run_date=close_time, 
                    args=[event_id, name],
                    id=f"close_{event_id}",
                    replace_existing=True
                )
                print(f" - Scheduled CLOSE for '{name}' at {close_time.strftime('%Y-%m-%d %H:%M:%S')} (Local Time)")

    except Exception as e:
        print(f"[{datetime.now()}] Error fetching or scheduling: {e}")

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.start()
    
    print("Starting Stream Opener Service (GUI Automation Mode)...")
    
    # Run fetch immediately
    fetch_and_schedule_events(scheduler)
    
    # Optionally, schedule the fetch function to run periodically (e.g., every hour) to get updates
    scheduler.add_job(fetch_and_schedule_events, 'interval', hours=1, args=[scheduler])
    
    try:
        # Keep the main thread alive
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        print("\nShutting down service...")
        scheduler.shutdown()
