import discord
from discord.ext import commands

import function as func

class HelpDropdown(discord.ui.Select):
    def __init__(self, categorys:list):
        self.view: HelpView

        super().__init__(
            placeholder="카테고리를 선택하세요!",
            min_values=1, max_values=1,
            options=[
                discord.SelectOption(emoji="🆕", label="정보", description="백설기의 새로운 업데이트 보기."),
            ] + [
                discord.SelectOption(emoji=emoji, label=f"{category} 명령어", description=f"이것은 {category.lower()} 카테고리입니다.")
                for category, emoji in zip(categorys, ["2️⃣", "3️⃣", "4️⃣"])
            ],
            custom_id="select"
        )
    
    async def callback(self, interaction: discord.Interaction) -> None:
        embed = self.view.build_embed(self.values[0].split(" ")[0])
        await interaction.response.edit_message(embed=embed)

class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot, author: discord.Member) -> None:
        super().__init__(timeout=60)

        self.author: discord.Member = author
        self.bot: commands.Bot = bot
        self.response: discord.Message = None
        self.categorys: list[str] = [ name.capitalize() for name, cog in bot.cogs.items() if len([c for c in cog.walk_commands()]) ]

        self.add_item(discord.ui.Button(label='초대', emoji=':invite:915152589056790589', url=f'https://discord.com/oauth2/authorize?client_id={bot.user.id}&permissions=8&scope=bot%20applications.commands'))
        self.add_item(discord.ui.Button(label='깃허브', emoji=':github:1098265017268322406', url='https://github.com/scottjsh/MusicBot'))
        self.add_item(HelpDropdown(self.categorys))
    
    async def on_error(self, error, item, interaction) -> None:
        return

    async def on_timeout(self) -> None:
        for child in self.children:
            if child.custom_id == "select":
                child.disabled = True
        try:
            await self.response.edit(view=self)
        except:
            pass

    async def interaction_check(self, interaction: discord.Interaction) -> None:
        return interaction.user == self.author

    def build_embed(self, category: str) -> discord.Embed:
        category = category.lower()
        if category == "news":
            embed = discord.Embed(title="백설기 도움말 메뉴", color=func.settings.embed_color)
            embed.add_field(
                name=f"카테고리: [{2 + len(self.categorys)}]",
                value="```py\n👉 정보\n{}```".format("".join(f"{i}. {c}\n" for i, c in enumerate(self.categorys, start=2))),
                inline=True
            )

            update = "백설기는 음악 봇입니다. YouTube, Soundcloud, Spotify, Twitch 등을 지원합니다!"
            embed.add_field(name="📰 정보:", value=update, inline=True)
            embed.add_field(name="시작하기", value="```음성 채널에 참여한 후 /play {노래/URL}로 노래를 재생하세요. (이름, 유튜브 비디오 링크, 재생 목록 링크 또는 스포티파이 링크가 지원됩니다.)```", inline=False)
            
            return embed

        embed = discord.Embed(title=f"카테고리: {category.capitalize()}", color=func.settings.embed_color)
        embed.add_field(name=f"카테고리: [{2 + len(self.categorys)}]", value="```py\n" + "\n".join(("👉 " if c == category.capitalize() else f"{i}. ") + c for i, c in enumerate(['정보'] + self.categorys, start=1)) + "```", inline=True)