import discord
import voicelink
import psutil
import function as func

from typing import Tuple
from discord import app_commands
from discord.ext import commands
from function import (
    LANGS,
    send,
    update_settings,
    get_settings,
    get_lang,
    time as ctime,
    get_aliases,
    cooldown_check
)
from views import DebugView, HelpView, EmbedBuilderView


def formatBytes(bytes: int, unit: bool = False):
    if bytes <= 1_000_000_000:
        return f"{bytes / (1024 ** 2):.1f}" + ("MB" if unit else "")

    else:
        return f"{bytes / (1024 ** 3):.1f}" + ("GB" if unit else "")


class Settings(commands.Cog, name="settings"):
    def __init__(self, bot) -> None:
        self.bot: commands.Bot = bot
        self.description = "이 카테고리는 서버의 관리자 권한을 가진 사용자만 이용할 수 있습니다."

    @commands.hybrid_group(
        name="settings",
        aliases=get_aliases("settings"),
        invoke_without_command=True
    )
    async def settings(self, ctx: commands.Context):
        view = HelpView(self.bot, ctx.author)
        embed = view.build_embed(self.qualified_name)
        view.response = await ctx.send(embed=embed, view=view)

    @settings.command(name="prefix", aliases=get_aliases("prefix"))
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def prefix(self, ctx: commands.Context, prefix: str):
        "메시지 명령어의 기본 접두사를 변경합니다."
        await update_settings(ctx.guild.id, {"$set": {"prefix": prefix}})
        await send(ctx, "setPrefix", prefix, prefix)

    @settings.command(name="language", aliases=get_aliases("language"))
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def language(self, ctx: commands.Context, language: str):
        "선호하는 언어를 선택할 수 있으며, 봇의 메시지가 설정한 언어로 변경됩니다."
        language = language.upper()
        if language not in LANGS:
            return await send(ctx, "languageNotFound")

        await update_settings(ctx.guild.id, {"$set": {'lang': language}})
        await send(ctx, 'changedLanguage', language)

    @language.autocomplete('language')
    async def autocomplete_callback(self, interaction: discord.Interaction, current: str) -> list:
        if current:
            return [app_commands.Choice(name=lang, value=lang) for lang in LANGS.keys() if current.upper() in lang]
        return [app_commands.Choice(name=lang, value=lang) for lang in LANGS.keys()]

    @settings.command(name="queue", aliases=get_aliases("queue"))
    @app_commands.choices(mode=[
        app_commands.Choice(name="공정한 대기열", value="FairQueue"),
        app_commands.Choice(name="일반 대기열", value="Queue")
    ])
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def queue(self, ctx: commands.Context, mode: str):
        "다른 유형의 대기열 모드로 전환합니다."
        mode = "FairQueue" if mode.lower() == "fairqueue" else "Queue"
        await update_settings(ctx.guild.id, {"$set": {"queueType": mode}})
        await send(ctx, "setqueue", mode)

    @settings.command(name="247", aliases=get_aliases("247"))
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def playforever(self, ctx: commands.Context):
        "24/7 모드를 켜고 끕니다. 이 모드는 자동으로 비활성화에 의한 연결 끊김을 방지합니다."
        settings = await get_settings(ctx.guild.id)
        toggle = settings.get('24/7', False)
        await update_settings(ctx.guild.id, {"$set": {'24/7': not toggle}})
        await send(ctx, '247', await get_lang(ctx.guild.id, "enabled" if not toggle else "disabled"))

    @settings.command(name="bypassvote", aliases=get_aliases("bypassvote"))
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def bypassvote(self, ctx: commands.Context):
        "투표 시스템을 켜고 끕니다."
        settings = await get_settings(ctx.guild.id)
        toggle = settings.get('votedisable', True)
        await update_settings(ctx.guild.id, {"$set": {'votedisable': not toggle}})
        await send(ctx, 'bypassVote', await get_lang(ctx.guild.id, "enabled" if not toggle else "disabled"))

    @settings.command(name="view", aliases=get_aliases("view"))
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def view(self, ctx: commands.Context):
        "서버의 모든 봇 설정을 보여줍니다."
        settings = await get_settings(ctx.guild.id)

        texts = await get_lang(ctx.guild.id, "settingsMenu", "settingsTitle", "settingsValue", "settingsTitle2", "settingsValue2", "settingsPermTitle", "settingsPermValue")
        embed = discord.Embed(color=func.settings.embed_color)
        embed.set_author(name=texts[0].format(
            ctx.guild.name), icon_url=self.bot.user.display_avatar.url)
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        embed.add_field(name=texts[1], value=texts[2].format(
            settings.get('prefix', func.settings.bot_prefix) or "None",
            settings.get('lang', 'KO'),
            settings.get('controller', True),
            f"<@&{settings['dj']}>" if 'dj' in settings else '`None`',
            settings.get('votedisable', False),
            settings.get('24/7', False),
            settings.get('volume', 100),
            ctime(settings.get('playTime', 0) * 60 * 1000),
            inline=True)
        )
        embed.add_field(name=texts[3], value=texts[4].format(
            settings.get("queueType", "Queue"),
            func.settings.max_queue,
            settings.get("duplicateTrack", True)
        ))

        perms = ctx.guild.me.guild_permissions
        embed.add_field(name=texts[5], value=texts[6].format(
            '<a:Check:941206936651706378>' if perms.administrator else '<a:Cross:941206918255497237>',
            '<a:Check:941206936651706378>' if perms.manage_guild else '<a:Cross:941206918255497237>',
            '<a:Check:941206936651706378>' if perms.manage_channels else '<a:Cross:941206918255497237>',
            '<a:Check:941206936651706378>' if perms.manage_messages else '<a:Cross:941206918255497237>'), inline=False
        )
        await ctx.send(embed=embed)

    @settings.command(name="volume", aliases=get_aliases("volume"))
    @app_commands.describe(value="정수를 입력하세요.")
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def volume(self, ctx: commands.Context, value: commands.Range[int, 1, 150]):
        "플레이어의 볼륨을 설정합니다."
        player: voicelink.Player = ctx.guild.voice_client
        if player:
            await player.set_volume(value, ctx.author)

        await update_settings(ctx.guild.id, {"$set": {'volume': value}})
        await send(ctx, 'setVolume', value)

    @settings.command(name="togglecontroller", aliases=get_aliases("togglecontroller"))
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def togglecontroller(self, ctx: commands.Context):
        "음악 컨트롤러를 켜고 끕니다."
        settings = await get_settings(ctx.guild.id)
        toggle = not settings.get('controller', True)

        player: voicelink.Player = ctx.guild.voice_client
        if player and toggle is False and player.controller:
            try:
                await player.controller.delete()
            except:
                discord.ui.View.from_message(player.controller).stop()

        await update_settings(ctx.guild.id, {"$set": {'controller': toggle}})
        await send(ctx, 'togglecontroller', await get_lang(ctx.guild.id, "enabled" if toggle else "disabled"))

    @settings.command(name="duplicatetrack", aliases=get_aliases("duplicatetrack"))
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def duplicatetrack(self, ctx: commands.Context):
        "대기열에 중복된 노래가 추가되지 않도록 설정합니다."
        settings = await get_settings(ctx.guild.id)
        toggle = not settings.get('duplicateTrack', False)
        player: voicelink.Player = ctx.guild.voice_client
        if player:
            player.queue._allow_duplicate = toggle

        await update_settings(ctx.guild.id, {"$set": {'duplicateTrack': toggle}})
        return await send(ctx, "toggleDuplicateTrack", await get_lang(ctx.guild.id, "disabled" if toggle else "enabled"))

    @settings.command(name="customcontroller", aliases=get_aliases("customcontroller"))
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def customcontroller(self, ctx: commands.Context):
        "음악 컨트롤러 임베드를 사용자 정의합니다."
        settings = await get_settings(ctx.guild.id)
        controller_settings = settings.get(
            "default_controller", func.settings.controller)

        view = EmbedBuilderView(ctx, controller_settings.get("embeds").copy())
        view.response = await ctx.send(embed=view.build_embed(), view=view)

    @settings.command(name="controllermsg", aliases=get_aliases("controllermsg"))
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def controllermsg(self, ctx: commands.Context):
        "음악 컨트롤러에서 버튼을 클릭할 때 메시지를 전송하는 기능을 켜고 끕니다."
        settings = await get_settings(ctx.guild.id)
        toggle = not settings.get('controller_msg', True)

        await update_settings(ctx.guild.id, {"$set": {'controller_msg': toggle}})
        await send(ctx, 'toggleControllerMsg', await get_lang(ctx.guild.id, "enabled" if toggle else "disabled"))

    @app_commands.command(name="debug")
    async def debug(self, interaction: discord.Interaction):
        if interaction.user.id not in func.settings.bot_access_user:
            return await interaction.response.send_message("이 명령어를 사용할 수 있는 권한이 없습니다!")

        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        available_memory, total_memory = memory.available, memory.total
        used_disk_space, total_disk_space = disk.used, disk.total
        embed = discord.Embed(
            title="📄 디버그 패널", color=func.settings.embed_color)
        embed.description = "```==    시스템 정보    ==\n" \
                            f"• CPU:     {psutil.cpu_freq().current}Mhz ({psutil.cpu_percent()}%)\n" \
                            f"• RAM:     {formatBytes(total_memory - available_memory)}/{formatBytes(total_memory, True)} ({memory.percent}%)\n" \
                            f"• DISK:    {formatBytes(total_disk_space - used_disk_space)}/{formatBytes(total_disk_space, True)} ({disk.percent}%)```"

        embed.add_field(
            name="🤖 봇 정보",
            value=f"```• 대기 시간: {self.bot.latency:.2f}ms\n"
                  f"• 서버 수:  {len(self.bot.guilds)}\n"
                  f"• 사용자 수:   {sum([guild.member_count for guild in self.bot.guilds])}\n"
                  f"• 플레이어 수: {len(self.bot.voice_clients)}```",
            inline=False
        )

        node: voicelink.Node
        for name, node in voicelink.NodePool._nodes.items():
            total_memory = node.stats.used + node.stats.free
            embed.add_field(
                name=f"{name} 노드 - " +
                ("🟢 연결됨" if node._available else "🔴 연결 끊김"),
                value=f"```• 주소:  {node._host}:{node._port}\n"
                      f"• 플레이어 수:  {len(node._players)}\n"
                      f"• CPU 사용률:      {node.stats.cpu_process_load:.1f}%\n"
                      f"• RAM:      {formatBytes(node.stats.free)}/{formatBytes(total_memory, True)} ({(node.stats.free/total_memory) * 100:.1f}%)\n"
                      f"• 대기 시간:  {node.latency:.2f}ms\n"
                      f"• 가동 시간:   {func.time(node.stats.uptime)}```",
                inline=True
            )

        await interaction.response.send_message(embed=embed, view=DebugView(self.bot), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Settings(bot))
