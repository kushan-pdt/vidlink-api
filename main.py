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
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--window-size=1920,1080"
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,
            is_mobile=False,
            has_touch=False,
            locale="en-US"
        )

        page = await context.new_page()

        # Intercept both requests and responses for .mpd or .m3u8
        def filter_url(req_url):
            if (".mpd" in req_url or ".m3u8" in req_url) and not captured_data["stream"]:
                if not any(x in req_url for x in ["sub", ".m4s", ".ts", "preview", "sprite"]):
                    captured_data["stream"] = req_url

        page.on("request", lambda req: filter_url(req.url))
        page.on("response", lambda res: filter_url(res.url))

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(5)

            # Try clicking multiple potential player areas
            click_points = [(960, 540), (500, 300), (600, 400), (400, 200)]
            for x, y in click_points:
                if captured_data["stream"]:
                    break
                await page.mouse.click(x, y)
                await asyncio.sleep(1.5)

            # Wait up to 15 seconds for network capture
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
                raise HTTPException(status_code=404, detail="Stream link not found")

        except Exception as e:
            await browser.close()
            raise HTTPException(status_code=500, detail=str(e))
