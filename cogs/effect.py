import discord
import voicelink

from function import (
    send,
    get_lang,
    get_aliases,
    cooldown_check
)
from discord import app_commands
from discord.ext import commands


async def check_access(ctx: commands.Context):
    player: voicelink.Player = ctx.guild.voice_client
    if not player:
        text = await get_lang(ctx.guild.id, "noPlayer")
        raise voicelink.exceptions.VoicelinkException(text)

    if ctx.author not in player.channel.members:
        if not ctx.author.guild_permissions.manage_guild:
            text = await get_lang(ctx.guild.id, "notInChannel")
            raise voicelink.exceptions.VoicelinkException(
                text.format(ctx.author.mention, player.channel.mention))

    return player


class Effect(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.description = "이 카테고리는 이 서버에서 DJ만 사용할 수 있습니다. (서버에서 DJ를 설정하려면 /settings setdj <DJ ROLE>을 사용하세요.)"

    async def effect_autocomplete(self, interaction: discord.Interaction, current: str) -> list:
        player: voicelink.Player = interaction.guild.voice_client
        if not player:
            return []
        if current:
            return [app_commands.Choice(name=effect.tag, value=effect.tag) for effect in player.filters.get_filters() if current in effect.tag]
        return [app_commands.Choice(name=effect.tag, value=effect.tag) for effect in player.filters.get_filters()]

    @commands.hybrid_command(name="speed", aliases=get_aliases("speed"))
    @app_commands.describe(value="속도를 설정할 값입니다. 기본값은 `1.0`입니다.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def speed(self, ctx: commands.Context, value: commands.Range[float, 0, 2]):
        "플레이어의 재생 속도를 설정합니다."
        player = await check_access(ctx)

        if player.filters.has_filter(filter_tag="speed"):
            player.filters.remove_filter(filter_tag="speed")
        await player.add_filter(voicelink.Timescale(tag="speed", speed=value))
        await ctx.send(f"속도를 **{value}**로 설정했습니다.")

    @commands.hybrid_command(name="karaoke", aliases=get_aliases("karaoke"))
    @app_commands.describe(
        level="카라오케의 레벨입니다. 기본값은 `1.0`입니다.",
        monolevel="카라오케의 모노 레벨입니다. 기본값은 `1.0`입니다.",
        filterband="카라오케의 필터 밴드입니다. 기본값은 `220.0`입니다.",
        filterwidth="카라오케의 필터 폭입니다. 기본값은 `100.0`입니다."
    )
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def karaoke(self, ctx: commands.Context, level: commands.Range[float, 0, 2] = 1.0, monolevel: commands.Range[float, 0, 2] = 1.0, filterband: commands.Range[float, 100, 300] = 220.0, filterwidth: commands.Range[float, 50, 150] = 100.0) -> None:
        "평등화(equalization)를 사용하여 보통 보컬을 대상으로 하는 필터입니다."
        player = await check_access(ctx)

        if player.filters.has_filter(filter_tag="karaoke"):
            player.filters.remove_filter(filter_tag="karaoke")
        await player.add_filter(voicelink.Karaoke(tag="karaoke", level=level, mono_level=monolevel, filter_band=filterband, filter_width=filterwidth))
        await send(ctx, "karaoke", level, monolevel, filterband, filterwidth)

    @commands.hybrid_command(name="tremolo", aliases=get_aliases("tremolo"))
    @app_commands.describe(
        frequency="트레몰로의 주파수입니다. 기본값은 `2.0`입니다.",
        depth="트레몰로의 깊이입니다. 기본값은 `0.5`입니다."
    )
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def tremolo(self, ctx: commands.Context, frequency: commands.Range[float, 0, 10] = 2.0, depth: commands.Range[float, 0, 1] = 0.5) -> None:
        "볼륨이 빠르게 진동하여 떨리는 효과를 생성하는 필터입니다."
        player = await check_access(ctx)

        if player.filters.has_filter(filter_tag="tremolo"):
            player.filters.remove_filter(filter_tag="tremolo")
        await player.add_filter(voicelink.Tremolo(tag="tremolo", frequency=frequency, depth=depth))
        await send(ctx, "tremolo&vibrato", frequency, depth)

    @commands.hybrid_command(name="vibrato", aliases=get_aliases("vibrato"))
    @app_commands.describe(
        frequency="비브라토의 주파수입니다. 기본값은 `2.0`입니다.",
        depth="비브라토의 깊이입니다. 기본값은 `0.5`입니다."
    )
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def vibrato(self, ctx: commands.Context, frequency: commands.Range[float, 0, 14] = 2.0, depth: commands.Range[float, 0, 1] = 0.5) -> None:
        "트레몰로와 유사하며, 볼륨이 진동하는 것이 아니라 음높이가 진동합니다."
        player = await check_access(ctx)

        if player.filters.has_filter(filter_tag="vibrato"):
            player.filters.remove_filter(filter_tag="vibrato")
        await player.add_filter(voicelink.Vibrato(tag="vibrato", frequency=frequency, depth=depth))
        await send(ctx, "tremolo&vibrato", frequency, depth)

    @commands.hybrid_command(name="rotation", aliases=get_aliases("rotation"))
    @app_commands.describe(hertz="회전의 주파수입니다. 기본값은 `0.2`입니다.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def rotation(self, ctx: commands.Context, hertz: commands.Range[float, 0, 2] = 0.2) -> None:
        "소리를 스테레오 채널/헤드폰 주위로 회전시키는 필터입니다."
        player = await check_access(ctx)

        if player.filters.has_filter(filter_tag="rotation"):
            player.filters.remove_filter(filter_tag="rotation")
        await player.add_filter(voicelink.Rotation(tag="rotation", rotation_hertz=hertz))
        await send(ctx, "rotation", hertz)

    @commands.hybrid_command(name="distortion", aliases=get_aliases("distortion"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def distortion(self, ctx: commands.Context) -> None:
        "디스토션 효과입니다. 독특한 오디오 효과를 생성할 수 있습니다."
        player = await check_access(ctx)

        if player.filters.has_filter(filter_tag="distortion"):
            player.filters.remove_filter(filter_tag="distortion")
        await player.add_filter(voicelink.Distortion(tag="distortion", sin_offset=0.0, sin_scale=1.0, cos_offset=0.0, cos_scale=1.0, tan_offset=0.0, tan_scale=1.0, offset=0.0, scale=1.0))
        await send(ctx, "distortion")

    @commands.hybrid_command(name="lowpass", aliases=get_aliases("lowpass"))
    @app_commands.describe(smoothing="로우패스 필터의 레벨입니다. 기본값은 `20.0`입니다.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def lowpass(self, ctx: commands.Context, smoothing: commands.Range[float, 10, 30] = 20.0) -> None:
        "고주파수를 억제하고 저주파수만 통과시키는 필터입니다."
        player = await check_access(ctx)

        if player.filters.has_filter(filter_tag="lowpass"):
            player.filters.remove_filter(filter_tag="lowpass")
        await player.add_filter(voicelink.LowPass(tag="lowpass", smoothing=smoothing))
        await send(ctx, "lowpass", smoothing)

    @commands.hybrid_command(name="channelmix", aliases=get_aliases("channelmix"))
    @app_commands.describe(
        left_to_left="왼쪽에서 왼쪽으로 소리를 보냅니다. 기본값은 `1.0`입니다.",
        right_to_right="오른쪽에서 오른쪽으로 소리를 보냅니다. 기본값은 `1.0`입니다.",
        left_to_right="왼쪽에서 오른쪽으로 소리를 보냅니다. 기본값은 `0.0`입니다.",
        right_to_left="오른쪽에서 왼쪽으로 소리를 보냅니다. 기본값은 `0.0`입니다."
    )
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def channelmix(self, ctx: commands.Context, left_to_left: commands.Range[float, 0, 1] = 1.0, right_to_right: commands.Range[float, 0, 1] = 1.0, left_to_right: commands.Range[float, 0, 1] = 0.0, right_to_left: commands.Range[float, 0, 1] = 0.0) -> None:
        "오디오의 팬닝을 수동으로 조정하는 필터입니다."
        player = await check_access(ctx)

        if player.filters.has_filter(filter_tag="channelmix"):
            player.filters.remove_filter(filter_tag="channelmix")
        await player.add_filter(voicelink.ChannelMix(tag="channelmix", left_to_left=left_to_left, right_to_right=right_to_right, left_to_right=left_to_right, right_to_left=right_to_left))
        await send(ctx, "channelmix", left_to_left, right_to_right, left_to_right, right_to_left)

    @commands.hybrid_command(name="nightcore", aliases=get_aliases("nightcore"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def nightcore(self, ctx: commands.Context) -> None:
        "플레이어에 나이트코어 필터를 추가합니다."
        player = await check_access(ctx)

        await player.add_filter(voicelink.Timescale.nightcore())
        await send(ctx, "nightcore")

    @commands.hybrid_command(name="8d", aliases=get_aliases("8d"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def eightD(self, ctx: commands.Context) -> None:
        "플레이어에 8D 필터를 추가합니다."
        player = await check_access(ctx)

        await player.add_filter(voicelink.Rotation.nightD())
        await send(ctx, "8d")

    @commands.hybrid_command(name="vaporwave", aliases=get_aliases("vaporwave"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def vaporwave(self, ctx: commands.Context) -> None:
        "플레이어에 베이퍼웨이브 필터를 추가합니다."
        player = await check_access(ctx)

        await player.add_filter(voicelink.Timescale.vaporwave())
        await send(ctx, "vaporwave")

    @commands.hybrid_command(name="cleareffect", aliases=get_aliases("cleareffect"))
    @app_commands.describe(effect="특정 사운드 효과를 제거합니다.")
    @app_commands.autocomplete(effect=effect_autocomplete)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def cleareffect(self, ctx: commands.Context, effect: str = None) -> None:
        "모든 사운드 효과 또는 특정 사운드 효과를 지웁니다."
        player = await check_access(ctx)

        if effect:
            await player.remove_filter(effect)
        else:
            await player.reset_filter()

        await send(ctx, "cleareffect")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Effect(bot))
