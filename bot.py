# language: Python, file: bot.py, target: Render Cloud (Linux), Python 3.11+
import os
import threading
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask

# Render Environment Variables에 DISCORD_TOKEN 등록 필수
TOKEN = os.environ.get("DISCORD_TOKEN", "").strip()

# 봇을 사용할 디스코드 서버 ID (숫자) — Render 환경변수 GUILD_ID로 넣어도 됨
GUILD_ID_RAW = os.environ.get("GUILD_ID", "여기에_서버_ID_숫자_입력").strip()

DEFAULT_COLOR = 0x5865F2

# --- Render Web Service 헬스체크용 초경량 서버 ---
app = Flask(__name__)


@app.route("/")
def health():
    return "OK", 200


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


def parse_hex_color(raw_hex: str) -> int:
    cleaned = (raw_hex or "").strip().lstrip("#")
    if len(cleaned) != 6:
        return DEFAULT_COLOR
    try:
        return int(cleaned, 16)
    except ValueError:
        return DEFAULT_COLOR


# --- 디스코드 임베드 작성 모달 ---
class EmbedBuilderModal(discord.ui.Modal, title="공지 임베드 작성"):
    embed_title = discord.ui.TextInput(
        label="제목 (큰 볼드 타이틀)",
        placeholder="예: 서비스명 | 공지 타이틀",
        required=True,
        max_length=256,
    )
    embed_body = discord.ui.TextInput(
        label="본문 내용 (줄바꿈 그대로 반영)",
        style=discord.TextStyle.paragraph,
        placeholder="**[ 안내 ]**\n원하는 내용을 자유롭게 입력",
        required=True,
        max_length=3400,
    )
    price_box = discord.ui.TextInput(
        label="하단 회색 박스 내용 (선택)",
        style=discord.TextStyle.paragraph,
        placeholder="[ 1일   : 15,000 ]\n[ 3일   : 25,000 ]\n[ 영구제 : 80,000 ]",
        required=False,
        max_length=500,
    )
    hex_color = discord.ui.TextInput(
        label="왼쪽 줄 색상 HEX (선택)",
        placeholder="5865F2",
        default="5865F2",
        required=False,
        max_length=7,
    )

    def __init__(
        self,
        target_channel: discord.abc.Messageable,
        attachment: discord.Attachment | None,
    ):
        super().__init__()
        self.target_channel = target_channel
        self.attachment = attachment

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        body_text = self.embed_body.value.strip()
        price_text = self.price_box.value.strip()

        description = body_text
        if price_text:
            description = f"{description}\n\n```text\n{price_text}\n```"

        embed = discord.Embed(
            title=self.embed_title.value.strip(),
            description=description,
            color=parse_hex_color(self.hex_color.value),
        )

        try:
            if self.attachment is not None:
                file = await self.attachment.to_file()
                embed.set_image(url=f"attachment://{file.filename}")
                await self.target_channel.send(file=file, embed=embed)
            else:
                await self.target_channel.send(embed=embed)

            channel_label = getattr(self.target_channel, "mention", "지정한 채널")
            await interaction.followup.send(
                f"{channel_label}에 임베드 전송을 완료했어.",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "전송 실패: 해당 채널에 메시지를 보낼 권한이 없어. 봇 권한을 확인해 줘.",
                ephemeral=True,
            )
        except discord.HTTPException as exc:
            await interaction.followup.send(
                f"전송 실패: 디스코드 API 오류가 발생했어. (`{exc.status}`)",
                ephemeral=True,
            )
        except Exception as exc:
            await interaction.followup.send(
                f"전송 실패: 예기치 못한 오류가 발생했어. (`{type(exc).__name__}`)",
                ephemeral=True,
            )


# --- 단일 서버 전용 봇 클래스 ---
class GuildEmbedBot(commands.Bot):
    def __init__(self, guild_id: int):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.guild_obj = discord.Object(id=guild_id)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=self.guild_obj)
        await self.tree.sync(guild=self.guild_obj)


def get_guild_id() -> int:
    if not GUILD_ID_RAW.isdigit():
        raise RuntimeError(
            "GUILD_ID가 올바른 숫자가 아니야. bot.py의 GUILD_ID_RAW 또는 Render 환경변수 GUILD_ID를 확인해 줘."
        )
    return int(GUILD_ID_RAW)


guild_id = get_guild_id()
bot = GuildEmbedBot(guild_id=guild_id)


@bot.tree.command(
    name="임베드",
    description="지정한 채널에 공지 임베드 카드를 직접 작성해 보냅니다.",
    guild=discord.Object(id=guild_id),
)
@app_commands.describe(
    채널="메시지를 보낼 대상 채널 (비우면 현재 채널)",
    이미지="카드 하단에 첨부할 이미지 파일 (선택)",
)
@app_commands.default_permissions(administrator=True)
async def send_embed_cmd(
    interaction: discord.Interaction,
    채널: discord.TextChannel | None = None,
    이미지: discord.Attachment | None = None,
):
    target: discord.abc.Messageable | None = 채널 or interaction.channel
    if target is None:
        await interaction.response.send_message(
            "대상 채널을 찾을 수 없어.",
            ephemeral=True,
        )
        return

    await interaction.response.send_modal(EmbedBuilderModal(target, 이미지))


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError(
            "DISCORD_TOKEN 환경변수가 비어 있어. Render Environment Variables에 등록해 줘."
        )
    threading.Thread(target=run_web, daemon=True).start()
    bot.run(TOKEN)
