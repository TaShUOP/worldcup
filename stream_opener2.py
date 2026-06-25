import asyncio
import os
import requests
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from playwright.async_api import async_playwright

API_URL = "https://api.ppv.to/api/streams"
TARGET_TAG = "fifa world cup"

class BrowserManager:
    def __init__(self):
        self.playwright = None
        self.windows = []  # List of dicts: {'context': context, 'page': page, 'is_free': True, 'id': 1}
        self.active_streams = {} # Maps event_id -> window_id

    async def start(self):
        print(f"[{datetime.now()}] Initializing dual-window Playwright setup...")
        self.playwright = await async_playwright().start()
        
        # We will create two profiles in the local directory
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        for i in range(1, 3):
            user_data_dir = os.path.join(base_dir, f'obs_profile_{i}')
            print(f"[{datetime.now()}] Launching permanent Window {i}...")
            context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                channel="chrome",
                headless=False,
                no_viewport=True,
                args=['--start-maximized']
            )
            
            # Ensure there is exactly one clean tab
            pages = context.pages
            if pages:
                page = pages[0]
                # Close any extra restored tabs
                for extra_page in pages[1:]:
                    await extra_page.close()
            else:
                page = await context.new_page()
                
            await page.goto("about:blank")
            await page.bring_to_front()
            
            self.windows.append({
                'context': context,
                'page': page,
                'is_free': True,
                'id': i
            })
        print(f"[{datetime.now()}] Both OBS windows are ready and locked!")

    async def stop(self):
        print(f"[{datetime.now()}] Shutting down browser contexts...")
        for win in self.windows:
            await win['context'].close()
        if self.playwright:
            await self.playwright.stop()

    async def open_stream(self, event_id, name, url):
        print(f"\n[{datetime.now()}] EVENT: Opening stream for '{name}'...")
        
        # Find a free window
        free_window = None
        for win in self.windows:
            if win['is_free']:
                free_window = win
                break
                
        if not free_window:
            print(f"[{datetime.now()}] ERROR: Both OBS windows are currently in use! Cannot open '{name}'.")
            return
            
        free_window['is_free'] = False
        self.active_streams[event_id] = free_window['id']
        page = free_window['page']
        
        try:
            print(f"[{datetime.now()}] Routing '{name}' to Window {free_window['id']}...")
            await page.bring_to_front()
            await page.goto(url, timeout=60000)
            
            # Wait 15 seconds for player to load
            await asyncio.sleep(15)
            
            # Click center
            viewport_size = page.viewport_size
            if viewport_size:
                x = viewport_size['width'] / 2
                y = viewport_size['height'] / 2
                await page.mouse.click(x, y)
                print(f"[{datetime.now()}] Auto-clicked center of Window {free_window['id']}.")
            else:
                await page.mouse.click(500, 500)
                
            print(f"[{datetime.now()}] Successfully started '{name}' on Window {free_window['id']}.")
        except Exception as e:
            print(f"[{datetime.now()}] ERROR opening '{name}' on Window {free_window['id']}: {e}")

    async def close_stream(self, event_id, name):
        print(f"\n[{datetime.now()}] EVENT: Closing stream for '{name}'...")
        window_id = self.active_streams.get(event_id)
        
        if not window_id:
            print(f"[{datetime.now()}] ERROR: Could not find active window for '{name}'.")
            return
            
        # Find the window object
        target_win = None
        for win in self.windows:
            if win['id'] == window_id:
                target_win = win
                break
                
        if target_win:
            try:
                page = target_win['page']
                await page.goto("about:blank")
                print(f"[{datetime.now()}] Successfully closed '{name}' and reset Window {window_id}.")
            except Exception as e:
                print(f"[{datetime.now()}] ERROR resetting Window {window_id}: {e}")
            finally:
                target_win['is_free'] = True
                del self.active_streams[event_id]

# Global instance
manager = BrowserManager()

async def fetch_and_schedule_events(scheduler):
    print(f"\n[{datetime.now()}] Fetching events from {API_URL}...")
    try:
        # Use run_in_executor for requests (blocking)
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, requests.get, API_URL)
        response.raise_for_status()
        data = response.json()

        target_events = []
        for category in data.get('streams', []):
            for event in category.get('streams', []):
                tags = []
                if event.get('tag'): tags.append(event['tag'].lower())
                if event.get('category_name'): tags.append(event['category_name'].lower())
                
                if TARGET_TAG.lower() in tags:
                    target_events.append(event)
        
        print(f"[{datetime.now()}] Found {len(target_events)} events matching '{TARGET_TAG}'.")
        
        now = datetime.now()

        for event in target_events:
            event_id = str(event.get('id', id(event)))
            name = event.get('name', 'Unknown Event')
            start_ts = event.get('starts_at')
            end_ts = event.get('ends_at')
            url = event.get('iframe') or f"https://ppv.to/event/{event.get('uri_name', '')}"

            if not all([start_ts, end_ts, url]):
                continue

            try:
                start_time = datetime.fromtimestamp(start_ts)
                end_time = datetime.fromtimestamp(end_ts)
            except (ValueError, TypeError):
                continue

            open_time = start_time - timedelta(minutes=10)
            close_time = end_time + timedelta(minutes=5)

            if close_time < now:
                continue

            # Schedule Open
            if open_time > now:
                scheduler.add_job(
                    manager.open_stream, 
                    'date', 
                    run_date=open_time, 
                    args=[event_id, name, url],
                    id=f"open_{event_id}",
                    replace_existing=True
                )
                print(f" - Scheduled OPEN for '{name}' at {open_time.strftime('%Y-%m-%d %H:%M:%S')} (Local Time)")
            elif start_time < now < end_time:
                print(f" - Event '{name}' is currently ongoing. Opening now.")
                await manager.open_stream(event_id, name, url)

            # Schedule Close
            if close_time > now:
                scheduler.add_job(
                    manager.close_stream, 
                    'date', 
                    run_date=close_time, 
                    args=[event_id, name],
                    id=f"close_{event_id}",
                    replace_existing=True
                )
                print(f" - Scheduled CLOSE for '{name}' at {close_time.strftime('%Y-%m-%d %H:%M:%S')} (Local Time)")

    except Exception as e:
        print(f"[{datetime.now()}] Error fetching or scheduling: {e}")

async def main():
    scheduler = AsyncIOScheduler()
    scheduler.start()
    
    print("Starting Stream Opener Service (Dual-Window Playwright Mode)...")
    await manager.start()
    
    await fetch_and_schedule_events(scheduler)
    
    # Schedule periodic polling
    scheduler.add_job(fetch_and_schedule_events, 'interval', hours=1, args=[scheduler])
    
    try:
        # Keep loop running
        while True:
            await asyncio.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        print("\nShutting down service...")
        scheduler.shutdown()
        await manager.stop()

if __name__ == "__main__":
    # Windows specific fix for asyncio and Playwright
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
