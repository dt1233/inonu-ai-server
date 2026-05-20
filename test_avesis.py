import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print("Arama sayfasi aciliyor...")
        await page.goto("https://avesis.inonu.edu.tr/arama?Bulunan%20Kay%C4%B1t%20T%C3%BCrleri[0]=Ara%C5%9Ft%C4%B1rmac%C4%B1lar&aranan=Hukuk")
        await page.wait_for_timeout(4000)
        
        html = await page.content()
        with open("test_avesis_search.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML test_avesis_search.html dosyasina kaydedildi.")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
