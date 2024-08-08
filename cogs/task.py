import voicelink
import discord
import function as func

from discord.ext import commands, tasks
from datetime import datetime
from addons import Placeholders


class Task(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.activity_update.start()  # 활동 업데이트 주기 시작
        self.player_check.start()     # 플레이어 상태 점검 주기 시작
        self.cache_cleaner.start()    # 캐시 청소 주기 시작

        # 활동 유형 설정
        self.act_type = {
            "play": discord.ActivityType.playing,
            "listen": discord.ActivityType.listening,
            "watch": discord.ActivityType.watching,
            "stream": discord.ActivityType.streaming
        }
        self.current_act = 0  # 현재 활동 인덱스
        self.placeholder = Placeholders(bot)  # 플레이스홀더 객체

    def cog_unload(self):
        # Cog이 언로드될 때 주기 작업 취소
        self.activity_update.cancel()
        self.player_check.cancel()
        self.cache_cleaner.cancel()

    @tasks.loop(minutes=10.0)
    async def activity_update(self):
        await self.bot.wait_until_ready()  # 봇이 준비될 때까지 대기

        try:
            # 설정에서 현재 활동 데이터 가져오기
            act_data = func.settings.activity[(
                self.current_act + 1) % len(func.settings.activity) - 1]

            act_original = self.bot.activity  # 현재 봇의 활동
            act_type = self.act_type.get(
                list(act_data.keys())[0].lower(), discord.ActivityType.playing)  # 활동 유형
            act_name = self.placeholder.replace(
                list(act_data.values())[0])  # 활동 이름

            # 현재 활동과 설정된 활동이 다르면 변경
            if act_original.type != act_type or act_original.name != act_name:
                new_act = discord.Activity(type=act_type, name=act_name)
                await self.bot.change_presence(activity=new_act)
                self.current_act = (
                    self.current_act + 1) % len(func.settings.activity)  # 다음 활동으로 인덱스 이동

        except:
            pass

    @tasks.loop(minutes=5.0)
    async def player_check(self):
        if not self.bot.voice_clients:  # 음성 클라이언트가 없으면 종료
            return

        player: voicelink.Player
        for player in self.bot.voice_clients:
            try:
                if not player.channel or not player.context or not player.guild:
                    await player.teardown()  # 플레이어 설정 해제
                    continue
            except:
                await player.teardown()  # 예외 발생 시 설정 해제
                continue

            members = player.channel.members
            # 재생 중이 아니고 큐가 비어있거나, 모든 멤버가 음소거 상태일 때
            if (not player.is_playing and player.queue.is_empty) or not any(False if member.bot or member.voice.self_deaf else True for member in members):
                if not player.settings.get('24/7', False):  # 24/7 모드가 아닐 경우
                    await player.teardown()  # 플레이어 설정 해제
                    continue
                else:
                    if not player.is_paused:
                        await player.set_pause(True)  # 일시 정지
            else:
                if not player.guild.me:
                    await player.teardown()  # 봇이 음성 채널에 없을 경우 설정 해제
                    continue
                elif not player.guild.me.voice:
                    # 봇이 음성 채널에 연결되지 않았을 경우 연결 시도
                    await player.connect(timeout=0.0, reconnect=True)

            try:
                if player.dj not in members:
                    for m in members:
                        if not m.bot:
                            player.dj = m  # DJ 설정
                            break
            except:
                pass

    @tasks.loop(hours=12.0)
    async def cache_cleaner(self):
        func.SETTINGS_BUFFER.clear()  # 설정 버퍼 청소
        func.USERS_BUFFER.clear()     # 사용자 버퍼 청소

        errorFile = func.gen_report()  # 오류 보고서 생성
        if errorFile:
            report_channel = self.bot.get_channel(
                func.report_channel_id)  # 보고서 채널 가져오기
            if report_channel:
                try:
                    # 보고서 전송
                    await report_channel.send(content=f"Report Before: <t:{round(datetime.timestamp(datetime.now()))}:F>", file=errorFile)
                except Exception as e:
                    print(f"보고서를 전송할 수 없습니다 (이유: {e})")
            func.ERROR_LOGS.clear()  # 오류 로그 청소


async def setup(bot: commands.Bot):
    await bot.add_cog(Task(bot))  # Task Cog을 봇에 추가
