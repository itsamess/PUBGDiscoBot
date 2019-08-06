import os
import pprint
import time
import discord
import asyncio
import pubg_python.exceptions
from var_dump import var_dump
from discord.ext.commands import Bot
from pubg_python import PUBG, Shard
from imgrender import renderImage
from config import config
from ratelimiter import RateLimiter
from database import DBManager


TIME_BETWEEN_CHECK = 600.0

db = DBManager()
rateLimiter = RateLimiter(10.0, 60.0)

pubg = PUBG(config['tokens']['pubg'], Shard.STEAM)
bot = Bot(command_prefix="!", pm_help=False)
bot.remove_command('help')

async def Looper():
  while True:
    print('loop')
    await bot.wait_until_ready()
    playerIds = db.PreparePlayerIds()
    await PubgGetPlayersData(playerIds)
    
    await asyncio.sleep(100)


async def PubgGetPlayersData(playerIds):
  playersChunks = list(chunk(playerIds, 10))
  for playerChunk in playersChunks:
    try: 
      await rateLimiter.wait()
      result = pubg.players().filter(player_ids=playerChunk)
      for player in result:
          db.UpdatePlayerLastCheck(player.id)
          await rateLimiter.wait()
          match = pubg.matches().get(player.matches[0])
          if not db.IsInAnalyzedMatches(player.id, match.id):
            db.InsertAnalyzedMatch(player.id, match.id)
            roster = findRosterByName(player.name, match.rosters)
            rank = roster.stats['rank']
            if(rank <= 100):
              authors = db.FindAuthorsByPlayerId(player.id)
              image = renderImage(match.map_name, match.game_mode, rank, roster.participants, len(match.rosters))
              mention = '@<{}>,'.format(*[x['id'] for x in authors])
              channel = bot.get_channel(authors[0]['channelId'])
              content = '{} Match: {}'.format(mention, match.id)
              await channel.send(content=content, file=discord.File(image))
              os.remove(image)
    except Exception as e:
      print(e)

def chunk(l, n):
  for i in range(0, len(l), n):
    yield l[i:i + n]

def findRosterByName(name, rosters):
  for roster in rosters:
    for participant in roster.participants:
      if participant.name == name:
        return roster

@bot.event
async def on_ready():
  activity = discord.Game(name=config['discord']['activity']['name'])
  await bot.change_presence(activity=activity)
  bot.loop.create_task(Looper())


@bot.command(pass_context=True)
async def track(ctx, playerName=None):
  author = ctx.message.author
  channel = ctx.message.channel

  if playerName is None: 
    return False
  
  if db.PlayerExists(playerName) is False:
    playerId = await PubgPlayerIdByName(playerName)
    if playerId == -1:
      return False
    else:
      if db.PlayerInsert(playerName, playerId) is False:
        return False #Player Not Found Error
  
  return db.IsAuthorTrackPlayer(author, channel, playerId)


async def PubgPlayerIdByName(playerName):
  try:
    await rateLimiter.wait()
    player = pubg.players().filter(player_names=[playerName])[0]
    return player.id

  except IndexError:
    return -1

  except pubg_python.exceptions.NotFoundError:
    print('NotFoundError')
    return -1

  except pubg_python.exceptions.RateLimitError:
    print('RateLimitError')
    await rateLimiter.wait()
    return await PubgPlayerIdByName(playerName)

try:
  bot.run(config['tokens']['discord'])

except discord.errors.LoginFailure as err:
  print(err)