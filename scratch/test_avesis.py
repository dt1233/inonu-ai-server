import asyncio
from playwright.async_api import async_playwright

async def test_avesis():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        print("Testing AVESIS Mühendislik...")
        await page.goto("https://avesis.inonu.edu.tr/arama?aranan=M%C3%BClhendislik", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        
        btn = page.locator("a:has-text('Araştırmacılar')").first
        if await btn.count() > 0:
            await btn.click()
            await page.wait_for_timeout(3000)
            
        print("Initial staff load...")
        cards = await page.query_selector_all(".researcher-card, .person-card, .card:has(.card-title), [class*='researcher']")
        print(f"Cards found: {len(cards)}")
        
        # Click next
        next_btn = page.locator(".pagination .sk-toggle__item:not(.is-disabled):has-text('›')").first
        if await next_btn.count() == 0:
            next_btn = page.locator("a[aria-label='Next'], li.next:not(.disabled) a").first
            
        if await next_btn.count() > 0:
            print("Clicking next...")
            await next_btn.click()
            # wait for network to settle or a new element?
            await page.wait_for_timeout(3000)
            cards2 = await page.query_selector_all(".researcher-card, .person-card, .card:has(.card-title), [class*='researcher']")
            print(f"Cards after next: {len(cards2)}")
            
            # Print the first person's name to see if it changed
            if cards2:
                name = await cards2[0].inner_text()
                print(f"First person on page 2: {name.split()[0]} {name.split()[1] if len(name.split()) > 1 else ''}")
        
        await browser.close()

asyncio.run(test_avesis())
