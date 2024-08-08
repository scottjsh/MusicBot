import discord
import voicelink
import re

from io import StringIO
from discord import app_commands
from discord.ext import commands
from function import (
    settings,
    send,
    time as ctime,
    formatTime,
    get_source,
    get_user,
    get_lang,
    truncate_string,
    cooldown_check,
    get_aliases
)

from addons import lyricsPlatform
from views import SearchView, ListView, LinkView, LyricsView, HelpView
from validators import url

searchPlatform = {
    "youtube": "ytsearch",
    "youtubemusic": "ytmsearch",
    "soundcloud": "scsearch",
    "apple": "amsearch",
}


async def nowplay(ctx: commands.Context, player: voicelink.Player):
    track = player.current
    if not track:
        return await send(ctx, 'noTrackPlaying', ephemeral=True)

    texts = await get_lang(ctx.guild.id, "nowplayingDesc", "nowplayingField", "nowplayingLink")
    upnext = "\n".join(f"`{index}.` `[{track.formatted_length}]` [{truncate_string(track.title)}]({track.uri})" for index, track in enumerate(
        player.queue.tracks()[:2], start=2))

    embed = discord.Embed(description=texts[0].format(
        track.title), color=settings.embed_color)
    embed.set_author(
        name=track.requester.display_name,
        icon_url=track.requester.display_avatar.url
    )
    embed.set_thumbnail(url=track.thumbnail)

    if upnext:
        embed.add_field(name=texts[1], value=upnext)

    pbar = "".join(":radio_button:" if i == round(
        player.position // round(track.length // 15)) else "▬" for i in range(15))
    icon = ":red_circle:" if track.is_stream else (
        ":pause_button:" if player.is_paused else ":arrow_forward:")
    embed.add_field(
        name="\u2800", value=f"{icon} {pbar} **[{ctime(player.position)}/{track.formatted_length}]**", inline=False)

    return await ctx.send(embed=embed, view=LinkView(texts[2].format(track.source), track.emoji, track.uri))


class Basic(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.description = "이 카테고리는 이 서버의 모든 사용자에게 제공됩니다. 특정 명령어에서는 투표가 필요합니다."
        self.ctx_menu = app_commands.ContextMenu(
            name="play",
            callback=self._play
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.ctx_menu.name, type=self.ctx_menu.type)

    async def help_autocomplete(self, interaction: discord.Interaction, current: str) -> list:
        return [app_commands.Choice(name=c.capitalize(), value=c) for c in self.bot.cogs if c not in ["Nodes", "Task"] and current in c]

    async def play_autocomplete(self, interaction: discord.Interaction, current: str) -> list:
        if voicelink.pool.URL_REGEX.match(current):
            return

        history: dict[str, str] = {}
        for track_id in reversed(await get_user(interaction.user.id, "history")):
            track_dict = voicelink.decode(track_id)
            history[track_dict["identifier"]] = track_dict

        history_tracks = [app_commands.Choice(name=truncate_string(
            f"🕒 {track['author']} - {track['title']}", 100), value=track['uri']) for track in history.values()][:25]
        if not current:
            return history_tracks

        node = voicelink.NodePool.get_node()
        if node and node.spotify_client:
            tracks: list[voicelink.Track] = await node.spotifySearch(current, requester=interaction.user)
            return history_tracks[:5] + [app_commands.Choice(name=f"🎵 {track.author} - {track.title}", value=f"{track.author} - {track.title}") for track in tracks]

    @commands.hybrid_command(name="connect", aliases=get_aliases("connect"))
    @app_commands.describe(channel="연결할 채널을 지정하세요.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def connect(self, ctx: commands.Context, channel: discord.VoiceChannel = None) -> None:
        "음성 채널에 연결합니다."
        try:
            player = await voicelink.connect_channel(ctx, channel)
        except discord.errors.ClientException:
            return await send(ctx, "alreadyConnected")

        await send(ctx, 'connect', player.channel)

    @commands.hybrid_command(name="play", aliases=get_aliases("play"))
    @app_commands.describe(query="쿼리 또는 검색 가능한 링크를 입력하세요.")
    @app_commands.autocomplete(query=play_autocomplete)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        "입력한 내용을 로드하여 큐에 추가합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            player = await voicelink.connect_channel(ctx)

        if not player.is_user_join(ctx.author):
            return await send(ctx, "notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        tracks = await player.get_tracks(query, requester=ctx.author)
        if not tracks:
            return await send(ctx, "noTrackFound")

        try:
            if isinstance(tracks, voicelink.Playlist):
                index = await player.add_track(tracks.tracks)
                await send(ctx, "playlistLoad", tracks.name, index)
            else:
                position = await player.add_track(tracks[0])
                texts = await get_lang(ctx.guild.id, "live", "trackLoad_pos", "trackLoad")
                await ctx.send((f"`{texts[0]}`" if tracks[0].is_stream else "") + (texts[1].format(tracks[0].title, tracks[0].uri, tracks[0].author, tracks[0].formatted_length, position) if position >= 1 and player.is_playing else texts[2].format(tracks[0].title, tracks[0].uri, tracks[0].author, tracks[0].formatted_length)), allowed_mentions=False)
        except voicelink.QueueFull as e:
            await ctx.send(e)
        finally:
            if not player.is_playing:
                await player.do_next()

    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def _play(self, interaction: discord.Interaction, message: discord.Message):
        query = ""

        if message.content:
            url = re.findall(
                r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", message.content)
            if url:
                query = url[0]

        elif message.attachments:
            query = message.attachments[0].url

        if not query:
            return await send(interaction, "noPlaySource", ephemeral=True)

        player: voicelink.Player = interaction.guild.voice_client
        if not player:
            player = await voicelink.connect_channel(interaction)

        if not player.is_user_join(interaction.user):
            return await send(interaction, "notInChannel", interaction.user.mention, player.channel.mention, ephemeral=True)

        tracks = await player.get_tracks(query, requester=interaction.user)
        if not tracks:
            return await send(interaction, "noTrackFound")

        try:
            if isinstance(tracks, voicelink.Playlist):
                index = await player.add_track(tracks.tracks)
                await send(interaction, "playlistLoad", tracks.name, index)
            else:
                position = await player.add_track(tracks[0])
                texts = await get_lang(interaction.guild.id, "live", "trackLoad_pos", "trackLoad")
                await interaction.response.send_message((f"`{texts[0]}`" if tracks[0].is_stream else "") + (texts[1].format(tracks[0].title, tracks[0].uri, tracks[0].author, tracks[0].formatted_length, position) if position >= 1 and player.is_playing else texts[2].format(tracks[0].title, tracks[0].uri, tracks[0].author, tracks[0].formatted_length)), allowed_mentions=False)
        except voicelink.QueueFull as e:
            await interaction.response.send_message(e)

        except Exception as e:
            return await interaction.response.send_message(e, ephemeral=True)

        finally:
            if not player.is_playing:
                await player.do_next()

    @commands.hybrid_command(name="search", aliases=get_aliases("search"))
    @app_commands.describe(
        query="노래 제목을 입력하세요.",
        platform="검색할 플랫폼을 선택하세요."
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="Youtube", value="Youtube"),
        app_commands.Choice(name="Youtube Music", value="YoutubeMusic"),
        app_commands.Choice(name="Spotify", value="Spotify"),
        app_commands.Choice(name="Apple", value="Apple"),
    ])
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def search(self, ctx: commands.Context, query: str, platform: str) -> None:
        "검색하고 트랙을 추가합니다."
        if platform not in searchPlatform:
            return await send(ctx, "invalidPlatform", ephemeral=True)

        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            player = await voicelink.connect_channel(ctx)

        if not player.is_user_join(ctx.author):
            return await send(ctx, "notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        tracks = await player.get_tracks(searchPlatform[platform](query), requester=ctx.author)
        if not tracks:
            return await send(ctx, "noTrackFound")

        try:
            if isinstance(tracks, voicelink.Playlist):
                index = await player.add_track(tracks.tracks)
                await send(ctx, "playlistLoad", tracks.name, index)
            else:
                position = await player.add_track(tracks[0])
                texts = await get_lang(ctx.guild.id, "live", "trackLoad_pos", "trackLoad")
                await ctx.send((f"`{texts[0]}`" if tracks[0].is_stream else "") + (texts[1].format(tracks[0].title, tracks[0].uri, tracks[0].author, tracks[0].formatted_length, position) if position >= 1 and player.is_playing else texts[2].format(tracks[0].title, tracks[0].uri, tracks[0].author, tracks[0].formatted_length)), allowed_mentions=False)
        except voicelink.QueueFull as e:
            await ctx.send(e)
        finally:
            if not player.is_playing:
                await player.do_next()

    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def _play(self, interaction: discord.Interaction, message: discord.Message):
        "유저의 메시지를 읽어 음악을 재생합니다."
        query = ""

        if message.content:
            url = re.findall(
                r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", message.content)
            if url:
                query = url[0]

        elif message.attachments:
            query = message.attachments[0].url

        if not query:
            return await send(interaction, "noPlaySource", ephemeral=True)

        player: voicelink.Player = interaction.guild.voice_client
        if not player:
            player = await voicelink.connect_channel(interaction)

        if not player.is_user_join(interaction.user):
            return await send(interaction, "notInChannel", interaction.user.mention, player.channel.mention, ephemeral=True)

        tracks = await player.get_tracks(query, requester=interaction.user)
        if not tracks:
            return await send(interaction, "noTrackFound")

        try:
            if isinstance(tracks, voicelink.Playlist):
                index = await player.add_track(tracks.tracks)
                await send(interaction, "playlistLoad", tracks.name, index)
            else:
                position = await player.add_track(tracks[0])
                texts = await get_lang(interaction.guild.id, "live", "trackLoad_pos", "trackLoad")
                await interaction.response.send_message((f"`{texts[0]}`" if tracks[0].is_stream else "") + (texts[1].format(tracks[0].title, tracks[0].uri, tracks[0].author, tracks[0].formatted_length, position) if position >= 1 and player.is_playing else texts[2].format(tracks[0].title, tracks[0].uri, tracks[0].author, tracks[0].formatted_length)), allowed_mentions=False)
        except voicelink.QueueFull as e:
            await interaction.response.send_message(e)

        except Exception as e:
            return await interaction.response.send_message(e, ephemeral=True)

        finally:
            if not player.is_playing:
                await player.do_next()

    @commands.hybrid_command(name="search", aliases=get_aliases("search"))
    @app_commands.describe(
        query="검색할 노래의 이름을 입력하세요.",
        platform="검색할 플랫폼을 선택하세요."
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="유튜브", value="Youtube"),
        app_commands.Choice(name="유튜브 뮤직", value="YoutubeMusic"),
        app_commands.Choice(name="스포티파이", value="Spotify"),
        app_commands.Choice(name="사운드클라우드", value="SoundCloud"),
        app_commands.Choice(name="애플 뮤직", value="Apple")
    ])
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def search(self, ctx: commands.Context, *, query: str, platform: str = "Youtube"):
        "입력한 쿼리를 로드하여 대기열에 추가합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            player = await voicelink.connect_channel(ctx)

        if not player.is_user_join(ctx.author):
            return await send(ctx, "notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        if url(query):
            return await send(ctx, "noLinkSupport", ephemeral=True)

        platform = platform.lower()
        if platform != 'spotify':
            query_platform = searchPlatform.get(
                platform, 'ytsearch') + f":{query}"
            tracks = await player.get_tracks(query=query_platform, requester=ctx.author)
        else:
            tracks = await player.node.spotifySearch(query=query, requester=ctx.author)

        if not tracks:
            return await send(ctx, "noTrackFound")

        texts = await get_lang(ctx.guild.id, "searchTitle", "searchDesc", "live", "trackLoad_pos", "trackLoad", "searchWait", "searchSuccess")
        query_track = "\n".join(
            f"`{index}.` `[{track.formatted_length}]` **{track.title[:35]}**" for index, track in enumerate(tracks[0:10], start=1))
        embed = discord.Embed(title=texts[0].format(query), description=texts[1].format(get_source(
            platform, "emoji"), platform, len(tracks[0:10]), query_track), color=settings.embed_color)
        view = SearchView(tracks=tracks[0:10], texts=[texts[5], texts[6]])
        view.response = await ctx.send(embed=embed, view=view, ephemeral=True)

        await view.wait()
        if view.values is not None:
            msg = ""
            for value in view.values:
                track = tracks[int(value.split(". ")[0]) - 1]
                position = await player.add_track(track)
                msg += (f"`{texts[2]}`" if track.is_stream else "") + (texts[3].format(track.title, track.uri, track.author, track.formatted_length,
                                                                                       position) if position >= 1 else texts[4].format(track.title, track.uri, track.author, track.formatted_length))
            await ctx.send(msg, allowed_mentions=False)

            if not player.is_playing:
                await player.do_next()

    @commands.hybrid_command(name="playtop", aliases=get_aliases("playtop"))
    @app_commands.describe(query="입력할 쿼리나 검색 가능한 링크를 입력하세요.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def playtop(self, ctx: commands.Context, *, query: str):
        "주어진 URL 또는 쿼리를 대기열의 맨 위에 추가합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            player = await voicelink.connect_channel(ctx)

        if not player.is_user_join(ctx.author):
            return await send(ctx, "notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        tracks = await player.get_tracks(query, requester=ctx.author)
        if not tracks:
            return await send(ctx, "noTrackFound")

        try:
            if isinstance(tracks, voicelink.Playlist):
                index = await player.add_track(tracks.tracks, at_font=True)
                await send(ctx, "playlistLoad", tracks.name, index)
            else:
                position = await player.add_track(tracks[0], at_font=True)
                texts = await get_lang(ctx.guild.id, "live", "trackLoad_pos", "trackLoad")
                await ctx.send((f"`{texts[0]}`" if tracks[0].is_stream else "") + (texts[1].format(tracks[0].title, tracks[0].uri, tracks[0].author, tracks[0].formatted_length, position) if position >= 1 and player.is_playing else texts[2].format(tracks[0].title, tracks[0].uri, tracks[0].author, tracks[0].formatted_length)), allowed_mentions=False)

        except voicelink.QueueFull as e:
            await ctx.send(e)

        finally:
            if not player.is_playing:
                await player.do_next()

    @commands.hybrid_command(name="forceplay", aliases=get_aliases("forceplay"))
    @app_commands.describe(query="입력할 쿼리나 검색 가능한 링크를 입력하세요.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def forceplay(self, ctx: commands.Context, query: str):
        "주어진 URL 또는 쿼리를 강제로 재생합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            player = await voicelink.connect_channel(ctx)

        if not player.is_privileged(ctx.author):
            return await send(ctx, "missingPerms_function", ephemeral=True)

        tracks = await player.get_tracks(query, requester=ctx.author)
        if not tracks:
            return await send(ctx, "noTrackFound")

        try:
            if isinstance(tracks, voicelink.Playlist):
                index = await player.add_track(tracks.tracks, at_font=True)
                await send(ctx, "playlistLoad", tracks.name, index)
            else:
                texts = await get_lang(ctx.guild.id, "live", "trackLoad")
                await player.add_track(tracks[0], at_font=True)
                await ctx.send((f"`{texts[0]}`" if tracks[0].is_stream else "") + texts[1].format(tracks[0].title, tracks[0].uri, tracks[0].author, tracks[0].formatted_length), allowed_mentions=False)

        except voicelink.QueueFull as e:
            await ctx.send(e)

        finally:
            if player.queue._repeat.mode == voicelink.LoopType.track:
                await player.set_repeat(voicelink.LoopType.off.name)

            await player.stop() if player.is_playing else await player.do_next()

    @commands.hybrid_command(name="pause", aliases=get_aliases("pause"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def pause(self, ctx: commands.Context):
        "음악을 일시 정지합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if player.is_paused:
            return await send(ctx, "pauseError", ephemeral=True)

        if not player.is_privileged(ctx.author):
            if ctx.author in player.pause_votes:
                return await send(ctx, "voted", ephemeral=True)
            else:
                player.pause_votes.add(ctx.author)
                if len(player.pause_votes) >= (required := player.required()):
                    pass
                else:
                    return await send(ctx, "pauseVote", ctx.author, len(player.pause_votes), required)

        await player.set_pause(True, ctx.author)
        player.pause_votes.clear()
        await send(ctx, "paused", ctx.author)

    @commands.hybrid_command(name="resume", aliases=get_aliases("resume"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def resume(self, ctx: commands.Context):
        "음악을 재개합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)
        if not player.is_paused:
            return await send(ctx, "resumeError")

        if not player.is_privileged(ctx.author):
            if ctx.author in player.resume_votes:
                return await send(ctx, "voted", ephemeral=True)
            else:
                player.resume_votes.add(ctx.author)
                if len(player.resume_votes) >= (required := player.required()):
                    pass
                else:
                    return await send(ctx, "resumeVote", ctx.author, len(player.resume_votes), required)

        await player.set_pause(False, ctx.author)
        player.resume_votes.clear()
        await send(ctx, "resumed", ctx.author)

    @commands.hybrid_command(name="skip", aliases=get_aliases("skip"))
    @app_commands.describe(index="건너뛰고 싶은 인덱스를 입력하세요.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def skip(self, ctx: commands.Context, index: int = 0):
        "다음 곡으로 건너뛰거나 지정된 곡으로 건너뜁니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_playing:
            return await send(ctx, "skipError", ephemeral=True)

        if not player.is_privileged(ctx.author):
            if ctx.author == player.current.requester:
                pass
            elif ctx.author in player.skip_votes:
                return await send(ctx, "voted", ephemeral=True)
            else:
                player.skip_votes.add(ctx.author)
                if len(player.skip_votes) >= (required := player.required()):
                    pass
                else:
                    return await send(ctx, "skipVote", ctx.author, len(player.skip_votes), required)

        if not player.node._available:
            return await send(ctx, "nodeReconnect")

        if index:
            player.queue.skipto(index)

        await send(ctx, "skipped", ctx.author)

        if player.queue._repeat.mode == voicelink.LoopType.track:
            await player.set_repeat(voicelink.LoopType.off.name)

        await player.stop()

    @commands.hybrid_command(name="back", aliases=get_aliases("back"))
    @app_commands.describe(index="되돌아가고 싶은 인덱스를 입력하세요.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def back(self, ctx: commands.Context, index: int = 1):
        "이전 곡으로 되돌아가거나 지정된 이전 곡으로 건너뜁니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            if ctx.author in player.previous_votes:
                return await send(ctx, "voted", ephemeral=True)
            else:
                player.previous_votes.add(ctx.author)
                if len(player.previous_votes) >= (required := player.required()):
                    pass
                else:
                    return await send(ctx, "backVote", ctx.author, len(player.previous_votes), required)

        if not player.node._available:
            return await send(ctx, "nodeReconnect")

        if not player.is_playing:
            player.queue.backto(index)
            await player.do_next()
        else:
            player.queue.backto(index + 1)
            await player.stop()

        await send(ctx, "backed", ctx.author)

        if player.queue._repeat.mode == voicelink.LoopType.track:
            await player.set_repeat(voicelink.LoopType.off.name)

    @commands.hybrid_command(name="seek", aliases=get_aliases("seek"))
    @app_commands.describe(position="위치를 입력하세요. 예: 1:20.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def seek(self, ctx: commands.Context, position: str):
        "플레이어의 위치를 변경합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send(ctx, "missingPerms_pos", ephemeral=True)

        if not player.current or player.position == 0:
            return await send(ctx, "noTrackPlaying", ephemeral=True)

        num = formatTime(position)
        if num is None:
            return await send(ctx, "timeFormatError", ephemeral=True)

        await player.seek(num, ctx.author)
        await send(ctx, "seek", position)

    @commands.hybrid_group(
        name="queue",
        aliases=get_aliases("queue"),
        fallback="list",
        invoke_without_command=True
    )
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def queue(self, ctx: commands.Context):
        "현재 대기열에 있는 곡들을 표시합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_user_join(ctx.author):
            return await send(ctx, "notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        if player.queue.is_empty:
            return await nowplay(ctx, player)
        view = ListView(player=player, author=ctx.author)
        view.response = await ctx.send(embed=await view.build_embed(), view=view)

    @queue.command(name="export", aliases=get_aliases("export"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def export(self, ctx: commands.Context):
        "대기열 전체를 텍스트 파일로 내보냅니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_user_join(ctx.author):
            return await send(ctx, "notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        if player.queue.is_empty and not player.current:
            return await send(ctx, "noTrackPlaying", ephemeral=True)

        await ctx.defer()

        tracks = player.queue.tracks(True)
        temp = ""
        raw = "----------->Raw Info<-----------\n"
        total_length = 0
        for index, track in enumerate(tracks, start=1):
            temp += f"{index}. {track.title} [{ctime(track.length)}]\n"
            raw += track.track_id
            if index != len(tracks):
                raw += ","
            total_length += track.length

        temp = "!이 파일을 변경하지 마세요!\n------------->정보<-------------\n서버: {} ({})\n요청자: {} ({})\n곡 수: {} - {}\n------------>곡들<------------\n".format(
            ctx.guild.name, ctx.guild.id,
            ctx.author.display_name, ctx.author.id,
            len(tracks), ctime(total_length)
        ) + temp
        temp += raw

        await ctx.reply(content="", file=discord.File(StringIO(temp), filename=f"{ctx.guild.id}_Full_Queue.txt"))

    @queue.command(name="import", aliases=get_aliases("import"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def _import(self, ctx: commands.Context, attachment: discord.Attachment):
        "텍스트 파일을 가져와 현재 대기열에 트랙을 추가합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            player = await voicelink.connect_channel(ctx)

        if not player.is_user_join(ctx.author):
            return await send(ctx, "notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        try:
            bytes = await attachment.read()
            track_ids = bytes.split(b"\n")[-1]
            track_ids = track_ids.decode().split(",")

            tracks = (voicelink.Track(track_id=track_id, info=voicelink.decode(
                track_id), requester=ctx.author) for track_id in track_ids)
            if not tracks:
                return await send(ctx, "noTrackFound")

            index = await player.add_track(tracks)
            await send(ctx, "playlistLoad", attachment.filename, index)

        except voicelink.QueueFull as e:
            return await ctx.send(e, ephemeral=True)

        except:
            return await send(ctx, "decodeError", ephemeral=True)

        finally:
            if not player.is_playing:
                await player.do_next()

    @commands.hybrid_command(name="history", aliases=get_aliases("history"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def history(self, ctx: commands.Context):
        "현재 대기열의 히스토리 곡들을 표시합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_user_join(ctx.author):
            return await send(ctx, "notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        if not player.queue.history():
            return await nowplay(ctx, player)

        view = ListView(player=player, author=ctx.author, is_queue=False)
        view.response = await ctx.send(embed=await view.build_embed(), view=view)

    @commands.hybrid_command(name="leave", aliases=get_aliases("leave"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def leave(self, ctx: commands.Context):
        "봇을 음성 채널에서 분리하고 대기열을 비웁니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            if ctx.author in player.stop_votes:
                return await send(ctx, "voted", ephemeral=True)
            else:
                player.stop_votes.add(ctx.author)
                if len(player.stop_votes) >= (required := player.required(leave=True)):
                    pass
                else:
                    return await send(ctx, "leaveVote", ctx.author, len(player.stop_votes), required)

        await send(ctx, "left", ctx.author)
        await player.teardown()

    @commands.hybrid_command(name="nowplaying", aliases=get_aliases("nowplaying"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def nowplaying(self, ctx: commands.Context):
        "현재 재생 중인 곡의 세부정보를 표시합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_user_join(ctx.author):
            return await send(ctx, "notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        await nowplay(ctx, player)

    @commands.hybrid_command(name="loop", aliases=get_aliases("loop"))
    @app_commands.describe(mode="루프 모드를 선택하세요.")
    @app_commands.choices(mode=[
        app_commands.Choice(name='Off', value='off'),
        app_commands.Choice(name='Track', value='track'),
        app_commands.Choice(name='Queue', value='queue')
    ])
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def loop(self, ctx: commands.Context, mode: str):
        "루프 모드를 변경합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send(ctx, "missingPerms_mode", ephemeral=True)

        await player.set_repeat(mode)
        await send(ctx, "repeat", mode.capitalize())

    @commands.hybrid_command(name="clear", aliases=get_aliases("clear"))
    @app_commands.describe(queue="비우고 싶은 대기열을 선택하세요.")
    @app_commands.choices(queue=[
        app_commands.Choice(name='Queue', value='queue'),
        app_commands.Choice(name='History', value='history')
    ])
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def clear(self, ctx: commands.Context, queue: str = "queue"):
        "대기열 또는 히스토리 대기열의 모든 곡을 제거합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send(ctx, "missingPerms_queue", ephemeral=True)

        queue = queue.lower()
        if queue == 'history':
            player.queue.history_clear(player.is_playing)
        else:
            queue = "queue"
            player.queue.clear()

        await send(ctx, "cleared", queue.capitalize())

    @commands.hybrid_command(name="remove", aliases=get_aliases("remove"))
    @app_commands.describe(
        position1="대기열에서 제거할 위치를 입력하세요.",
        position2="제거할 대기열의 범위를 설정하세요.",
        member="특정 멤버가 요청한 트랙을 제거하세요."
    )
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def remove(self, ctx: commands.Context, position1: int, position2: int = None, member: discord.Member = None):
        "지정된 트랙 또는 트랙 범위를 대기열에서 제거합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send(ctx, "missingPerms_queue", ephemeral=True)

        removedTrack = player.queue.remove(position1, position2, member=member)

        if player.is_ipc_connected and removedTrack:
            await player.send_ws({
                "op": "removeTrack",
                "positions": [track["position"] for track in removedTrack],
                "track_ids": [track["track"].track_id for track in removedTrack],
                "current_queue_position": player.queue._position
            }, requester=ctx.author)

        await send(ctx, "removed", len(removedTrack))

    @commands.hybrid_command(name="forward", aliases=get_aliases("forward"))
    @app_commands.describe(position="앞으로 이동할 시간을 입력하세요. 예: 1:20")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def forward(self, ctx: commands.Context, position: str = "10"):
        "현재 곡에서 특정 시간만큼 앞으로 이동합니다. 기본값은 10초입니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send(ctx, "missingPerms_pos", ephemeral=True)

        if not player.current:
            return await send(ctx, "noTrackPlaying", ephemeral=True)

        num = formatTime(position)
        if num is None:
            return await send(ctx, "timeFormatError", ephemeral=True)

        await player.seek(int(player.position + num))
        await send(ctx, "forward", ctime(player.position + num))

    @commands.hybrid_command(name="rewind", aliases=get_aliases("rewind"))
    @app_commands.describe(position="뒤로 이동할 시간을 입력하세요. 예: 1:20")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def rewind(self, ctx: commands.Context, position: str = "10"):
        "현재 곡에서 특정 시간만큼 뒤로 이동합니다. 기본값은 10초입니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send(ctx, "missingPerms_pos", ephemeral=True)

        if not player.current:
            return await send(ctx, "noTrackPlaying", ephemeral=True)

        num = formatTime(position)
        if num is None:
            return await send(ctx, "timeFormatError", ephemeral=True)

        await player.seek(int(player.position - num))
        await send(ctx, "rewind", ctime(player.position - num))

    @commands.hybrid_command(name="replay", aliases=get_aliases("replay"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def replay(self, ctx: commands.Context):
        "현재 곡의 진행 상황을 리셋합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send(ctx, "missingPerms_pos", ephemeral=True)

        if not player.current:
            return await send(ctx, "noTrackPlaying", ephemeral=True)

        await player.seek(0)
        await send(ctx, "replay")
    @commands.hybrid_command(name="shuffle", aliases=get_aliases("shuffle"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def shuffle(self, ctx: commands.Context):
        "대기열의 곡들을 무작위로 섞습니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            if ctx.author in player.shuffle_votes:
                return await send(ctx, "voted", ephemeral=True)
            else:
                player.shuffle_votes.add(ctx.author)
                if len(player.shuffle_votes) >= (required := player.required()):
                    pass
                else:
                    return await send(ctx, "shuffleVote", ctx.author, len(player.shuffle_votes), required)
        
        await player.shuffle("queue", ctx.author)
        await send(ctx, "shuffled")

    @commands.hybrid_command(name="swap", aliases=get_aliases("swap"))
    @app_commands.describe(
        position1="교환할 트랙의 위치. 예: 2",
        position2="position1과 교환할 트랙의 위치. 예: 1"
    )
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def swap(self, ctx: commands.Context, position1: int, position2: int):
        "지정된 두 곡을 교환합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send(ctx, "missingPerms_pos", ephemeral=True)

        track1, track2 = player.queue.swap(position1, position2)
        await player.send_ws({
            "op": "swapTrack",
            "position1": {"index": position1, "track_id": track1.track_id},
            "position2": {"index": position2, "track_id": track2.track_id}
        }, requester=ctx.author)
        await send(ctx, "swapped", track1.title, track2.title)

    @commands.hybrid_command(name="move", aliases=get_aliases("move"))
    @app_commands.describe(
        target="이동할 트랙의 위치. 예: 2",
        to="트랙을 이동할 새로운 위치. 예: 1"
    )
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def move(self, ctx: commands.Context, target: int, to: int):
        "지정된 트랙을 새로운 위치로 이동합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)
        
        if not player.is_privileged(ctx.author):
            return await send(ctx, "missingPerms_pos", ephemeral=True)

        moved_track = player.queue.move(target, to)
        await player.send_ws({
            "op": "moveTrack",
            "position": {"index": target, "track_id": moved_track.track_id},
            "newPosition": {"index": to}
        }, requester=ctx.author)
        await send(ctx, "moved", moved_track, to)

    @commands.hybrid_command(name="lyrics", aliases=get_aliases("lyrics"))
    @app_commands.describe(title="쿼리를 검색하여 반환된 가사를 표시합니다.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def lyrics(self, ctx: commands.Context, title: str = "", artist: str = ""):
        "현재 재생 중인 곡의 가사를 표시합니다."
        if not title:
            player: voicelink.Player = ctx.guild.voice_client
            if not player or not player.is_playing:
                return await send(ctx, "noTrackPlaying", ephemeral=True)
            
            title = player.current.title
            artist = player.current.author
        
        await ctx.defer()
        song: dict[str, str] = await lyricsPlatform.get(settings.lyrics_platform)().get_lyrics(title, artist)
        if not song:
            return await send(ctx, "lyricsNotFound", ephemeral=True)

        view = LyricsView(name=title, source={_: re.findall(r'.*\n(?:.*\n){,22}', v) for _, v in song.items()}, author=ctx.author)
        view.response = await ctx.send(embed=view.build_embed(), view=view)

    @commands.hybrid_command(name="swapdj", aliases=get_aliases("swapdj"))
    @app_commands.describe(member="DJ 역할을 이전할 멤버를 선택하세요.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def swapdj(self, ctx: commands.Context, member: discord.Member):
        "DJ 역할을 다른 멤버에게 이전합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_user_join(ctx.author):
            return await send(ctx, "notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        if player.dj.id != ctx.author.id or player.settings.get('dj', False):
            return await send(ctx, "notdj", f"<@&{player.settings['dj']}>" if player.settings.get('dj') else player.dj.mention, ephemeral=True)

        if player.dj.id == member.id or member.bot:
            return await send(ctx, "djToMe", ephemeral=True)

        if member not in player.channel.members:
            return await send(ctx, "djnotinchannel", member, ephemeral=True)

        player.dj = member
        await send(ctx, "djswap", member)

    @commands.hybrid_command(name="autoplay", aliases=get_aliases("autoplay"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def autoplay(self, ctx: commands.Context):
        "자동 재생 모드를 전환합니다. 이 모드에서는 가장 적합한 곡들이 자동으로 대기열에 추가됩니다."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send(ctx, "noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send(ctx, "missingPerms_autoplay", ephemeral=True)

        check = not player.settings.get("autoplay", False)
        player.settings['autoplay'] = check
        await send(ctx, "autoplay", await get_lang(ctx.guild.id, "enabled" if check else "disabled"))

        if not player.is_playing:
            await player.do_next()

    @commands.hybrid_command(name="help", aliases=get_aliases("help"))
    @app_commands.autocomplete(category=help_autocomplete)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def help(self, ctx: commands.Context, category: str = "News") -> None:
        "Vocard의 모든 명령어를 나열합니다."
        if category not in self.bot.cogs:
            category = "News"
        view = HelpView(self.bot, ctx.author)
        embed = view.build_embed(category)
        view.response = await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="ping", aliases=get_aliases("ping"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def ping(self, ctx: commands.Context):
        "봇이 작동 중인지 확인하고, 명령어와 응답 간의 지연 시간을 확인합니다."
        player: voicelink.Player = ctx.guild.voice_client

        value = await get_lang(ctx.guild.id, "pingTitle1", "pingfield1", "pingTitle2", "pingfield2")
        
        embed = discord.Embed(color=settings.embed_color)
        embed.add_field(
            name=value[0],
            value=value[1].format(
                "0", "0", self.bot.latency, '😭' if self.bot.latency > 5 else ('😨' if self.bot.latency > 1 else '👌'), "St Louis, MO, United States"
        ))

        if player:
            embed.add_field(
                name=value[2],
                value=value[3].format(
                    player.node._identifier, player.ping, player.node.player_count, player.channel.rtc_region),
                    inline=False
            )

        await ctx.send(embed=embed)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Basic(bot))
