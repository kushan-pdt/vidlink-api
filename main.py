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
        # Browser with cloud flags
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        def handle_request(request):
            req_url = request.url
            if ".mpd" in req_url and not captured_data["stream"]:
                captured_data["stream"] = req_url

        page.on("request", handle_request)

        try:
            await page.goto(url, timeout=60000)
            await asyncio.sleep(4)

            await page.mouse.click(500, 300)

            for _ in range(12):
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
