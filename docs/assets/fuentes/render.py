import sys, asyncio
from playwright.async_api import async_playwright

async def main(src, out, width=1780, scale=2, full=True, wait=350):
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--force-color-profile=srgb",
                                          "--font-render-hinting=none"])
        pg = await b.new_page(viewport={"width": width, "height": 1200},
                              device_scale_factor=scale)
        await pg.goto("file://" + src)
        await pg.wait_for_timeout(wait)
        await pg.screenshot(path=out, full_page=full)
        dims = await pg.evaluate("[document.body.scrollWidth, document.body.scrollHeight]")
        print("css size:", dims)
        await b.close()

if __name__ == "__main__":
    src, out = sys.argv[1], sys.argv[2]
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 1780
    asyncio.run(main(src, out, width=w))
