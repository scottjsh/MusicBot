import voicelink
import asyncio
import discord
import function as func

from discord.ext import commands

class Listeners(commands.Cog):
    """음악 관련 Cog입니다."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voicelink = voicelink.NodePool()

        bot.loop.create_task(self.start_nodes())
        
    async def start_nodes(self) -> None:
        """노드를 연결하고 초기화합니다."""
        await self.bot.wait_until_ready()
        for n in func.settings.nodes.values():
            try:
                await self.voicelink.create_node(
                    bot=self.bot, 
                    spotify_client_id=func.tokens.spotify_client_id, 
                    spotify_client_secret=func.tokens.spotify_client_secret,
                    **n
                )
            except Exception as e:
                print(f'노드 {n["identifier"]}가 연결할 수 없습니다! - 이유: {e}')

    @commands.Cog.listener()
    async def on_voicelink_track_end(self, player: voicelink.Player, track, _):
        await player.do_next()

    @commands.Cog.listener()
    async def on_voicelink_track_stuck(self, player: voicelink.Player, track, _):
        await asyncio.sleep(10)
        await player.do_next()

    @commands.Cog.listener()
    async def on_voicelink_track_exception(self, player: voicelink.Player, track, error: dict):
        try:
            player._track_is_stuck = True
            await player.context.send(f"{error['message']}! 다음 곡이 5초 후에 시작됩니다.", delete_after=10)
        except:
            pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        
        if before.channel == after.channel:
            return

        player: voicelink.Player = member.guild.voice_client
        if not player:
            return
        
        guild = member.guild.id
        is_joined = True
        
        if not before.channel and after.channel:
            if after.channel.id != player.channel.id:
                return

        elif before.channel and not after.channel:
            is_joined = False
        
        elif before.channel and after.channel:
            if after.channel.id != player.channel.id:
                is_joined = False
                
        if player.is_ipc_connected:
            await self.bot.ipc.send({
                "op": "updateGuild",
                "user": {
                    "user_id": member.id,
                    "avatar_url": member.display_avatar.url,
                    "name": member.name,
                },
                "channel_name": member.voice.channel.name if is_joined else "",
                "guild_id": guild,
                "is_joined": is_joined
            })

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Listeners(bot))
