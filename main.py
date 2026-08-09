import asyncio
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "API is running"}

@app.get("/get-stream/{media_type}/{tmdb_id}")
async def get_stream(
    media_type: str, 
    tmdb_id: str, 
    season: int = Query(default=1), 
    episode: int = Query(default=1)
):
    media_type = media_type.lower()
    
    if media_type == "movie":
        url = f"https://vidlink.pro/movie/{tmdb_id}"
    elif media_type == "tv":
        url = f"https://vidlink.pro/tv/{tmdb_id}/{season}/{episode}"
    else:
        raise HTTPException(status_code=400, detail="Invalid media_type. Use 'movie' or 'tv'.")

    captured_data = {"stream": None}

    async with async_playwright() as p:
        # Chromium launch options to bypass anti-bot mechanisms
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--window-size=1920,1080"
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,
            is_mobile=False,
            has_touch=False,
            locale="en-US",
            timezone_id="America/New_York"
        )

        page = await context.new_page()

        # Intercept network requests for stream manifests
        def handle_request(request):
            req_url = request.url
            if (".mpd" in req_url or ".m3u8" in req_url) and not captured_data["stream"]:
                # Ignore subtitle or segment files
                if not ("sub" in req_url or ".m4s" in req_url or ".ts" in req_url):
                    captured_data["stream"] = req_url

        page.on("request", handle_request)

        try:
            # Navigate to page with commit wait
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)

            # Interact with player to trigger network stream loading
            await page.mouse.click(600, 400)
            await asyncio.sleep(2)
            await page.mouse.click(600, 400)

            # Poll for stream link up to 15 seconds
            for _ in range(15):
                if captured_data["stream"]:
                    break
                await asyncio.sleep(1)

            await browser.close()

            if captured_data["stream"]:
                return {
                    "success": True,
                    "media_type": media_type,
                    "tmdb_id": tmdb_id,
                    "stream_link": captured_data["stream"]
                }
            else:
                raise HTTPException(status_code=404, detail="404: Stream link not found")

        except Exception as e:
            await browser.close()
            raise HTTPException(status_code=500, detail=str(e))
