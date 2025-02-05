import requests
from lxml import html
import re
from threading import Thread
from queue import Queue
import time
import discord
from discord.ext import commands

TOKEN = ""


intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

futures = {}


ua = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-encoding': 'gzip, deflate, br, zstd',
    'accept-language': 'en-US,en;q=0.9',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
    'priority': 'u=0, i',
    'referer': 'https://www.ebay.com/sch/i.html?_from=R40&_nkw=ufc+rookies&_sacat=0&_fcid=1',
    'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
    'sec-ch-ua-full-version': '"132.0.6834.160"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-model': '""',
    'sec-ch-ua-platform': '"Windows"',
    'sec-ch-ua-platform-version': '"19.0.0"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36'
}


def getEbayItemsByKeyword(keyword):
    try:
        query_url = f'https://www.ebay.com/sch/i.html?_from=R40&_nkw={
            keyword}&_sacat=0&_fcid=1&_sop=10&rt=nc&LH_BIN=1'
        res = requests.get(query_url, headers=ua)
        p = html.fromstring(res.text)
        x = p.xpath('//div[@id="srp-river-results"]//li')
        n = len(x)
        items = []
        for i in range(n):
            title = x[i].xpath('.//span[@role="heading"]/text()')
            if len(title) == 0:
                continue
            item = {}
            price = x[i].xpath('.//span[@class="s-item__price"]/text()')
            seller = x[i].xpath(
                './/span[@class="s-item__seller-info-text"]/text()')
            image_urls = x[i].xpath('.//img/@src')
            image = ''
            for image_url in image_urls:
                if image_url.find('/s-l') != -1:
                    image = image_url.replace('.webp', '.jpg')
                    break

            urls = x[i].xpath('.//a/@href')
            for url in urls:
                if url.find('/itm/') != -1:
                    item_id = re.findall(r'/itm/([0-9]+)', url)
                    item['url'] = 'https://www.ebay.com/itm/' + item_id[0]
                    item['id'] = item_id[0]
                    break
            try:
                item['title'] = title[0]
                item['price'] = price[0]
                item['seller'] = seller[0]
                item['image'] = image
                items.append(item)
            except:
                continue
        return items
    except Exception as e:
        print(e)
        return []


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')




@bot.event
async def on_guild_channel_delete(channel):
    channel_id = channel.id
    if futures.get(channel_id) is not None:
        future = futures[channel_id]
        future.state = 'stopped'
        del futures[channel_id]
        print("Worker stopped")
    else:
        print("Worker is not running")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    await bot.process_commands(message)


@bot.command(name="keyword", help="Update the keywords for the worker")
async def keyword(ctx, *, keywords: str):
    keywords = [kw.strip() for kw in keywords.split(",")]

    channel_id = ctx.channel.id
    if futures.get(channel_id) is not None:
        future = futures[channel_id]
        future.state = 'stopped'
        del futures[channel_id]

    future = ebayWatcher(keywords, channel_id)
    future.start()
    futures[channel_id] = future
    await ctx.send("New worker started with keywords: " + str(keywords))


@bot.command(name="start", help="Start new worker")
async def keyword(ctx):

    channel_id = ctx.channel.id
    if futures.get(channel_id) is None:
        keyword = ctx.channel.name.replace('-', ' ')
        future = ebayWatcher([keyword], channel_id)
        future.start()
        futures[channel_id] = future
        await ctx.send("New worker started")
    else:
        await ctx.send("Worker is already running")


@bot.command(name="stop", help="Stop the worker")
async def keyword(ctx):

    channel_id = ctx.channel.id
    if futures.get(channel_id) is not None:
        future = futures[channel_id]
        future.state = 'stopped'
        del futures[channel_id]
        await ctx.send("Worker stopped")
    else:
        await ctx.send("Worker is not running")


def build_embeded_message(item, caption):
    text_message = f"**[{item['title']}]({item['url']})**"
    embed = discord.Embed(description=text_message, color=discord.Color.blue())
    embed.title = caption
    embed.set_image(url=item['image'])
    embed.add_field(name="Details:", value=f"Seller: {
                    item['seller']}\nPrice: {item['price']}", inline=False)
    return embed

import traceback
class ebayWatcher(Thread):
    def __init__(self, keywords, channel_id):
        super().__init__()
        self.keywords = keywords
        self.channel_id = channel_id
        self.state = 'running'
        self.latest_item_id = None
        self.delay = 2
        self.previous_items = []

    def run(self):
        channel_name = None
        try:
            i = 0
            while self.state == 'running':
                items = getEbayItemsByKeyword(self.keywords[i % len(self.keywords)])
                i += 1
                if len(items) == 0:
                    continue
                caption = None
                if self.latest_item_id is None:
                    latest_item = items[0]
                    self.latest_item_id = latest_item['id']
                    self.previous_items.append(self.latest_item_id)
                    print('[*] Initial item id set:', self.latest_item_id)
                    caption = 'This is the latest item found on eBay'

                elif self.latest_item_id != items[0]['id']:
                    latest_item = items[0]
                    if latest_item['id'] in self.previous_items:
                        continue
                    self.latest_item_id = latest_item['id']
                    self.previous_items.append(self.latest_item_id)
                    caption = 'New item has been listed on eBay'
                else:
                    continue
                message = build_embeded_message(latest_item, caption)
                channel = bot.get_channel(self.channel_id)
                channel_name = channel.name
                bot.loop.create_task(channel.send(embed=message))
                time.sleep(self.delay)
            print('[*] Worker stopped for channel:',
                  self.channel_id, 'with keyword:', self.keywords)
        except Exception as e:
            traceback.print_exc()
            print(f'ebayWatcher[ #channel {channel_name} ] [ #keywords {self.keywords} ] -> ', e)
            return


bot.run(TOKEN)
