import discord
import voicelink

from io import StringIO
from discord import app_commands
from discord.ext import commands
from function import (
    send,
    time as ctime,
    get_user,
    update_user,
    check_roles,
    get_lang,
    settings,
    get_aliases,
    cooldown_check
)

from datetime import datetime
from views import PlaylistView, InboxView, HelpView


def assign_playlistId(existed: list) -> str:
    for i in range(200, 210):
        if str(i) not in existed:
            return str(i)


async def check_playlist_perms(user_id: int, author_id: int, d_id: str) -> dict:
    playlist = await get_user(author_id, 'playlist')
    playlist = playlist.get(d_id)
    if not playlist or user_id not in playlist['perms']['read']:
        return {}
    return playlist


async def check_playlist(ctx: commands.Context, name: str = None, full: bool = False, share: bool = True) -> dict:
    user = await get_user(ctx.author.id, 'playlist')

    await ctx.defer()
    if full:
        return user

    if not name:
        return {'playlist': user['200'], 'position': 1, 'id': "200"}

    for index, data in enumerate(user, start=1):
        playlist = user[data]
        if playlist['name'].lower() == name:
            if playlist['type'] == 'share' and share:
                playlist = await check_playlist_perms(ctx.author.id, playlist['user'], playlist['referId'])
                if not playlist or ctx.author.id not in playlist['perms']['read']:
                    return {'playlist': None, 'position': index, 'id': data}
            return {'playlist': playlist, 'position': index, 'id': data}
    return {'playlist': None, 'position': None, 'id': None}


async def search_playlist(url: str, requester: discord.Member, time_needed: bool = True) -> dict:
    try:
        tracks = await voicelink.NodePool.get_node().get_tracks(url, requester=requester)
        tracks = {"name": tracks.name, "tracks": tracks.tracks}
        if time_needed:
            time = sum([track.length for track in tracks["tracks"]])
    except:
        return {}

    if time_needed:
        tracks["time"] = ctime(time)

    return tracks


class Playlists(commands.Cog, name="playlist"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.description = "이것은 Vocard 재생 목록 시스템입니다. 즐겨찾기를 저장하고 Vocard를 사용하여 모든 서버에서 재생할 수 있습니다."

    async def playlist_autocomplete(self, interaction: discord.Interaction, current: str) -> list:
        playlists_raw: dict[str, dict] = await get_user(interaction.user.id, 'playlist')
        playlists = [value['name']
                     for value in playlists_raw.values()] if playlists_raw else []
        if current:
            return [app_commands.Choice(name=p, value=p) for p in playlists if current in p]
        return [app_commands.Choice(name=p, value=p) for p in playlists]

    @commands.hybrid_group(
        name="playlist",
        aliases=get_aliases("playlist"),
        invoke_without_command=True
    )
    async def playlist(self, ctx: commands.Context):
        view = HelpView(self.bot, ctx.author)
        embed = view.build_embed(self.qualified_name)
        view.response = await ctx.send(embed=embed, view=view)

    @playlist.command(name="play", aliases=get_aliases("play"))
    @app_commands.describe(
        name="사용자 지정 재생 목록의 이름을 입력하세요.",
        value="사용자 지정 재생 목록에서 특정 트랙을 재생합니다."
    )
    @app_commands.autocomplete(name=playlist_autocomplete)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def play(self, ctx: commands.Context, name: str = None, value: int = None) -> None:
        "즐겨찾기 재생 목록의 모든 노래를 재생합니다."
        result = await check_playlist(ctx, name.lower() if name else None)

        if not result['playlist']:
            return await send(ctx, 'playlistNotFound', name, ephemeral=True)
        rank, max_p, max_t = check_roles()
        if result['position'] > max_p:
            return await send(ctx, 'playlistNotAccess', ephemeral=True)

        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            player = await voicelink.connect_channel(ctx)

        if result['playlist']['type'] == 'link':
            tracks = await search_playlist(result['playlist']['uri'], ctx.author, time_needed=False)
        else:
            if not result['playlist']['tracks']:
                return await send(ctx, 'playlistNoTrack', result['playlist']['name'], ephemeral=True)

            playtrack = []
            for track in result['playlist']['tracks'][:max_t]:
                playtrack.append(voicelink.Track(
                    track_id=track, info=voicelink.decode(track), requester=ctx.author))

            tracks = {"name": result['playlist']['name'], "tracks": playtrack}

        if not tracks:
            return await send(ctx, 'playlistNoTrack', result['playlist']['name'], ephemeral=True)

        if value and 0 < value <= (len(tracks['tracks'])):
            tracks['tracks'] = [tracks['tracks'][value - 1]]
        await player.add_track(tracks['tracks'])
        await send(ctx, 'playlistPlay', result['playlist']['name'], len(tracks['tracks'][:max_t]))

        if not player.is_playing:
            await player.do_next()

    @playlist.command(name="view", aliases=get_aliases("view"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def view(self, ctx: commands.Context) -> None:
        "모든 재생 목록과 즐겨찾기 재생 목록의 모든 노래를 나열합니다."
        user = await check_playlist(ctx, full=True)
        rank, max_p, max_t = check_roles()

        results = []
        for index, data in enumerate(user, start=1):
            playlist = user[data]
            time = 0
            try:
                if playlist['type'] == 'link':
                    tracks = await search_playlist(playlist['uri'], requester=ctx.author)
                    results.append({'emoji': ('🔒' if max_p < index else '🔗'), 'id': data, 'time': tracks['time'], 'name': playlist[
                                   'name'], 'tracks': tracks['tracks'], 'perms': playlist['perms'], 'type': playlist['type']})

                else:
                    if share := playlist['type'] == 'share':
                        playlist = await check_playlist_perms(ctx.author.id, playlist['user'], playlist['referId'])
                        if not playlist:
                            await update_user(ctx.author.id, {"$unset": {f"playlist.{data}": 1}})
                            continue

                        if playlist['type'] == 'link':
                            tracks = await search_playlist(playlist['uri'], requester=ctx.author)
                            results.append({'emoji': ('🔒' if max_p < index else '🤝'), 'id': data, 'time': tracks['time'], 'name': user[data][
                                           'name'], 'tracks': tracks['tracks'], 'perms': playlist['perms'], 'owner': user[data]['user'], 'type': 'share'})
                            continue

                    init = []
                    for track in playlist['tracks']:
                        dt = voicelink.decode(track)
                        time += dt.get("length", 0)
                        init.append(dt)
                    playlist['tracks'] = init
                    results.append({'emoji': ('🔒' if max_p < index else ('🤝' if share else '❤️')), 'id': data, 'time': ctime(
                        time), 'name': user[data]['name'], 'tracks': playlist['tracks'], 'perms': playlist['perms'], 'owner': user[data].get('user', None), 'type': user[data]['type']})

            except:
                results.append({'emoji': '⛔', 'id': data, 'time': '--', 'name': user[data]['name'], 'tracks': [
                ], 'perms': user[data].get('perms', {}), 'type': user[data].get('type', '')})

        await ctx.send(view=PlaylistView(ctx.author, results))

    @playlist.command(name="create", aliases=get_aliases("create"))
    @app_commands.describe(name="재생 목록의 이름을 입력하세요.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def create(self, ctx: commands.Context, name: str) -> None:
        "새 재생 목록을 생성합니다."
        user = await get_user(ctx.author.id, 'playlist')
        if len(user) > 200:
            return await send(ctx, 'playlistLimitExceeded', ephemeral=True)

        if any(p['name'].lower() == name.lower() for p in user.values()):
            return await send(ctx, 'playlistAlreadyExists', name, ephemeral=True)

        id = assign_playlistId(list(user.keys()))
        if id:
            await update_user(ctx.author.id, {"$set": {f"playlist.{id}": {'name': name, 'type': 'regular', 'tracks': []}}})
            await send(ctx, 'playlistCreated', name)
        else:
            await send(ctx, 'playlistFailedToCreate', ephemeral=True)

    @playlist.command(name="delete", aliases=get_aliases("delete"))
    @app_commands.describe(name="삭제할 재생 목록의 이름을 입력하세요.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def delete(self, ctx: commands.Context, name: str) -> None:
        "재생 목록을 삭제합니다."
        result = await check_playlist(ctx, name.lower() if name else None)

        if not result['playlist']:
            return await send(ctx, 'playlistNotFound', name, ephemeral=True)
        if result['playlist']['type'] == 'share':
            await send(ctx, 'playlistNotDeletable', name, ephemeral=True)
            return

        await update_user(ctx.author.id, {"$unset": {f"playlist.{result['id']}": 1}})
        await send(ctx, 'playlistDeleted', name)

    @playlist.command(name="rename", aliases=get_aliases("rename"))
    @app_commands.describe(name="재생 목록의 새 이름을 입력하세요.", new_name="새 재생 목록의 이름을 입력하세요.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def rename(self, ctx: commands.Context, name: str, new_name: str) -> None:
        "재생 목록의 이름을 변경합니다."
        result = await check_playlist(ctx, name.lower() if name else None)

        if not result['playlist']:
            return await send(ctx, 'playlistNotFound', name, ephemeral=True)

        user = await get_user(ctx.author.id, 'playlist')
        if any(p['name'].lower() == new_name.lower() for p in user.values()):
            return await send(ctx, 'playlistAlreadyExists', new_name, ephemeral=True)

        await update_user(ctx.author.id, {"$set": {f"playlist.{result['id']}.name": new_name}})
        await send(ctx, 'playlistRenamed', new_name)

    @playlist.command(name="share", aliases=get_aliases("share"))
    @app_commands.describe(name="공유할 재생 목록의 이름을 입력하세요.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def share(self, ctx: commands.Context, name: str) -> None:
        "재생 목록을 공유합니다."
        result = await check_playlist(ctx, name.lower() if name else None)
        if not result['playlist']:
            return await send(ctx, 'playlistNotFound', name, ephemeral=True)

        if result['playlist']['type'] == 'share':
            return await send(ctx, 'playlistAlreadyShared', name, ephemeral=True)

        id = assign_playlistId([key for key in await get_user(ctx.author.id, 'playlist')])
        if not id:
            return await send(ctx, 'playlistShareFailed', ephemeral=True)
        await update_user(ctx.author.id, {"$set": {f"playlist.{id}": {'name': result['playlist']['name'], 'type': 'share', 'tracks': result['playlist']['tracks'], 'user': ctx.author.id, 'referId': result['id'], 'perms': {'read': [ctx.author.id]}}}})
        await send(ctx, 'playlistShared', name)

    @playlist.command(name="add", aliases=get_aliases("add"))
    @app_commands.describe(name="재생 목록에 추가할 트랙의 URL을 입력하세요.")
    async def add(self, ctx: commands.Context, name: str, url: str) -> None:
        "재생 목록에 트랙을 추가합니다."
        result = await check_playlist(ctx, name.lower() if name else None)
        if not result['playlist']:
            return await send(ctx, 'playlistNotFound', name, ephemeral=True)

        if result['playlist']['type'] == 'share':
            return await send(ctx, 'playlistNotEditable', name, ephemeral=True)

        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            player = await voicelink.connect_channel(ctx)

        tracks = await search_playlist(url, ctx.author, time_needed=False)
        if not tracks:
            return await send(ctx, 'playlistTrackNotFound', ephemeral=True)

        await update_user(ctx.author.id, {"$push": {f"playlist.{result['id']}.tracks": tracks['tracks']}})
        await send(ctx, 'playlistTrackAdded', name)

    @playlist.command(name="remove", aliases=get_aliases("remove"))
    @app_commands.describe(name="재생 목록에서 제거할 트랙의 번호를 입력하세요.")
    async def remove(self, ctx: commands.Context, name: str, index: int) -> None:
        "재생 목록에서 트랙을 제거합니다."
        result = await check_playlist(ctx, name.lower() if name else None)
        if not result['playlist']:
            return await send(ctx, 'playlistNotFound', name, ephemeral=True)

        if result['playlist']['type'] == 'share':
            return await send(ctx, 'playlistNotEditable', name, ephemeral=True)

        if not (0 < index <= len(result['playlist']['tracks'])):
            return await send(ctx, 'playlistTrackNotFound', ephemeral=True)

        track = result['playlist']['tracks'].pop(index - 1)
        await update_user(ctx.author.id, {"$set": {f"playlist.{result['id']}.tracks": result['playlist']['tracks']}})
        await send(ctx, 'playlistTrackRemoved', name)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Playlists(bot))
