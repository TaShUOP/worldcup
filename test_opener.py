import requests
import time
import webbrowser
import pyautogui
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

API_URL = "https://api.ppv.to/api/streams"
TARGET_NAME = "rally tv"

def open_stream(event_id, name, url):
    print(f"\n[{datetime.now()}] TEST: Opening stream for '{name}'...")
    try:
        # Open in default browser natively (avoids all profile lock issues)
        webbrowser.open(url)
        
        # Wait 15 seconds for the player to load
        time.sleep(15)
        
        # Click the center of the screen
        screen_width, screen_height = pyautogui.size()
        pyautogui.click(screen_width / 2, screen_height / 2)
        
        print(f"[{datetime.now()}] TEST: Auto-clicked center of screen.")
        print(f"[{datetime.now()}] TEST: Successfully opened '{name}'.")
    except Exception as e:
        print(f"[{datetime.now()}] TEST: Error opening '{name}': {e}")

def close_stream(event_id, name):
    print(f"\n[{datetime.now()}] TEST: Closing stream for '{name}'...")
    try:
        # Use Ctrl+W to close the active tab
        pyautogui.hotkey('ctrl', 'w')
        print(f"[{datetime.now()}] TEST: Successfully closed '{name}'.")
    except Exception as e:
        print(f"[{datetime.now()}] TEST: Error closing '{name}': {e}")

def fetch_and_schedule_events(scheduler):
    print(f"\n[{datetime.now()}] Fetching events from {API_URL}...")
    try:
        response = requests.get(API_URL)
        response.raise_for_status()
        data = response.json()

        target_events = []
        for category in data.get('streams', []):
            for event in category.get('streams', []):
                name = event.get('name', '').lower()
                tags = [t.lower() for t in [event.get('tag'), event.get('category_name')] if t]
                
                # Check for "rally tv" in name or tags
                if TARGET_NAME in name or TARGET_NAME in tags:
                    target_events.append(event)
                    break 
            if target_events:
                break
        
        if not target_events:
            print(f"[{datetime.now()}] TEST: Could not find '{TARGET_NAME}' in API. Using a dummy fallback for testing.")
            target_events = [{
                'id': 'dummy_test_123',
                'name': 'Rally TV (Dummy Fallback)',
                'iframe': 'https://www.youtube.com/embed/dQw4w9WgXcQ?autoplay=1' 
            }]

        now = datetime.now() 

        for event in target_events:
            event_id = str(event.get('id', id(event)))
            name = event.get('name', 'Unknown Event')
            url = event.get('iframe') or f"https://ppv.to/event/{event.get('uri_name', '')}"

            # 1 second from now to open
            open_time = now + timedelta(seconds=1)
            # 5 minutes from now to close
            close_time = now + timedelta(minutes=1)

            print(f"[{datetime.now()}] TEST: Found target event '{name}'.")
            
            # Schedule Open
            scheduler.add_job(
                open_stream, 
                'date', 
                run_date=open_time, 
                args=[event_id, name, url],
                id=f"open_{event_id}",
                replace_existing=True
            )
            print(f" - TEST: Scheduled OPEN for '{name}' at {open_time.strftime('%H:%M:%S')}")

            # Schedule Close
            scheduler.add_job(
                close_stream, 
                'date', 
                run_date=close_time, 
                args=[event_id, name],
                id=f"close_{event_id}",
                replace_existing=True
            )
            print(f" - TEST: Scheduled CLOSE for '{name}' at {close_time.strftime('%H:%M:%S')}")

    except Exception as e:
        print(f"[{datetime.now()}] Error fetching or scheduling: {e}")

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.start()
    
    print("Starting TEST Stream Opener Service (GUI Automation Mode)...")
    fetch_and_schedule_events(scheduler)
    
    try:
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        print("\nShutting down service...")
        scheduler.shutdown()
