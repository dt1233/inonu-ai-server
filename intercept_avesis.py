import asyncio
import json
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        # Intercept and log POST requests containing "search"
        page.on("request", lambda request: 
            print(f"URL: {request.url}\nData: {request.post_data}") 
            if request.method == "POST" and ("search" in request.url or "api" in request.url) else None
        )
        
        await page.goto("https://avesis.inonu.edu.tr/arama?aranan=Hukuk")
        await page.wait_for_timeout(5000)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
