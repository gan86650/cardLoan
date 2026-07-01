import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import database as db


class Loans(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _ensure_user(self, user: discord.User | discord.Member):
        await db.upsert_user(str(user.id), user.display_name)

    # ── /借牌 ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="借牌", description="記錄你跟某人借了牌")
    @app_commands.describe(
        牌主="牌的擁有者（你跟誰借）",
        卡名="卡名",
        版本="版本／版號（可選，例如 EN-001、Alpha）",
        數量="數量（預設 1）",
        備註="備註（可選）",
    )
    async def borrow(
        self,
        interaction: discord.Interaction,
        牌主: discord.Member,
        卡名: str,
        版本: Optional[str] = None,
        數量: Optional[int] = 1,
        備註: Optional[str] = None,
    ):
        if 牌主.id == interaction.user.id:
            await interaction.response.send_message("不能跟自己借牌 😅", ephemeral=True)
            return
        if 數量 < 1:
            await interaction.response.send_message("數量至少為 1", ephemeral=True)
            return

        await self._ensure_user(interaction.user)
        await self._ensure_user(牌主)
        await db.add_loan(
            str(interaction.guild_id),
            str(牌主.id),
            str(interaction.user.id),
            卡名.strip(),
            版本.strip() if 版本 else None,
            數量,
            備註,
        )
        qty_str = f" x{數量}" if 數量 > 1 else ""
        edition_str = f" [{版本}]" if 版本 else ""
        await interaction.response.send_message(
            f"✅ 已記錄：**{interaction.user.display_name}** 跟 **{牌主.display_name}** 借了 **{卡名}{edition_str}{qty_str}**"
        )

    @borrow.autocomplete("卡名")
    async def card_autocomplete(self, interaction: discord.Interaction, current: str):
        cards = await db.get_card_autocomplete(current)
        return [app_commands.Choice(name=c, value=c) for c in cards]

    # ── /借出去的牌 ────────────────────────────────────────────────────────────
    @app_commands.command(name="借出去的牌", description="查看你借出去、還沒還的牌")
    async def mylent(self, interaction: discord.Interaction):
        await self._ensure_user(interaction.user)
        loans = await db.get_active_loans_by_lender(str(interaction.user.id))

        groups: dict[str, list] = {}
        for loan in loans:
            groups.setdefault(loan["borrower_name"], []).append(loan)

        if not groups:
            await interaction.response.send_message("目前沒有借出去的牌 ✅", ephemeral=True)
            return

        embed = discord.Embed(title="📤 你借出去的牌", colour=discord.Colour.orange())
        for borrower, items in groups.items():
            lines = []
            for loan in items:
                qty = f" x{loan['quantity']}" if loan['quantity'] > 1 else ""
                edition = f" [{loan['edition']}]" if loan['edition'] else ""
                date = loan['borrowed_at'].strftime('%Y-%m-%d')
                lines.append(f"`#{loan['id']}` {loan['card_name']}{edition}{qty} — {date}")
            embed.add_field(name=f"👤 {borrower}", value="\n".join(lines), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /借進來的牌 ────────────────────────────────────────────────────────────
    @app_commands.command(name="借進來的牌", description="查看你借進來、還沒還的牌")
    async def myborrowed(self, interaction: discord.Interaction):
        await self._ensure_user(interaction.user)
        loans = await db.get_active_loans_by_borrower(str(interaction.user.id))

        groups: dict[str, list] = {}
        for loan in loans:
            groups.setdefault(loan["lender_name"], []).append(loan)

        if not groups:
            await interaction.response.send_message("你目前沒有借任何人的牌 ✅", ephemeral=True)
            return

        embed = discord.Embed(title="📥 你借進來的牌", colour=discord.Colour.blue())
        for lender, items in groups.items():
            lines = []
            for loan in items:
                qty = f" x{loan['quantity']}" if loan['quantity'] > 1 else ""
                edition = f" [{loan['edition']}]" if loan['edition'] else ""
                date = loan['borrowed_at'].strftime('%Y-%m-%d')
                lines.append(f"`#{loan['id']}` {loan['card_name']}{edition}{qty} — {date}")
            embed.add_field(name=f"👤 {lender}", value="\n".join(lines), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /查借牌 ────────────────────────────────────────────────────────────────
    @app_commands.command(name="查借牌", description="查看你跟某人之間的借貸狀況")
    @app_commands.describe(對象="要查詢的對象")
    async def check(self, interaction: discord.Interaction, 對象: discord.Member):
        await self._ensure_user(interaction.user)
        await self._ensure_user(對象)
        loans = await db.get_loans_between(str(interaction.user.id), str(對象.id))

        embed = discord.Embed(
            title=f"🔍 你與 {對象.display_name} 的借牌紀錄",
            colour=discord.Colour.green(),
        )
        if not loans:
            embed.description = "目前沒有未還紀錄 ✅"
        else:
            for loan in loans:
                qty = f" x{loan['quantity']}" if loan['quantity'] > 1 else ""
                edition = f" [{loan['edition']}]" if loan['edition'] else ""
                date = loan['borrowed_at'].strftime('%Y-%m-%d')
                direction = (
                    f"← {loan['lender_name']} 借給你"
                    if loan["borrower_id"] == str(interaction.user.id)
                    else f"→ 你借給 {loan['borrower_name']}"
                )
                embed.add_field(
                    name=f"`#{loan['id']}` {loan['card_name']}{edition}{qty}",
                    value=f"{direction} · {date}",
                    inline=False,
                )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /還牌 ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="還牌", description="標記牌已歸還（用借牌紀錄的 ID）")
    @app_commands.describe(紀錄id="借牌紀錄 ID（從 /借進來的牌 查詢）")
    async def return_card(self, interaction: discord.Interaction, 紀錄id: int):
        success = await db.return_loan(紀錄id, str(interaction.user.id))
        if success:
            await interaction.response.send_message(f"✅ 紀錄 #{紀錄id} 已標記為歸還")
        else:
            await interaction.response.send_message(
                f"找不到 #{紀錄id}，或這筆紀錄不是你借的", ephemeral=True
            )

    # ── /借牌總覽 ─────────────────────────────────────────────────────────────
    @app_commands.command(name="借牌總覽", description="顯示伺服器所有未還紀錄（公開）")
    async def loans(self, interaction: discord.Interaction):
        all_loans = await db.get_all_active_loans(str(interaction.guild_id))
        if not all_loans:
            await interaction.response.send_message("伺服器目前沒有任何未還紀錄 ✅")
            return

        groups: dict[str, list] = {}
        for loan in all_loans:
            groups.setdefault(loan["borrower_name"], []).append(loan)

        embed = discord.Embed(
            title=f"📋 伺服器借牌總覽（共 {len(all_loans)} 筆）",
            colour=discord.Colour.gold(),
        )
        for borrower, items in groups.items():
            lines = []
            for loan in items:
                qty = f" x{loan['quantity']}" if loan['quantity'] > 1 else ""
                edition = f" [{loan['edition']}]" if loan['edition'] else ""
                date = loan['borrowed_at'].strftime('%Y-%m-%d')
                lines.append(
                    f"`#{loan['id']}` {loan['card_name']}{edition}{qty} ← **{loan['lender_name']}** · {date}"
                )
            embed.add_field(name=f"👤 {borrower}", value="\n".join(lines), inline=False)

        await interaction.response.send_message(embed=embed)

    # ── /指令說明 ─────────────────────────────────────────────────────────────
    @app_commands.command(name="指令說明", description="顯示所有可用指令")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📖 TCG 借牌追蹤系統 — 指令說明",
            colour=discord.Colour.blurple(),
        )
        embed.add_field(
            name="📥 /借牌 @牌主 卡名 [版本] [數量] [備註]",
            value="記錄你跟某人借了牌\n例：`/借牌 @小明 Robogon of Starfall Ridge EN-001 2`",
            inline=False,
        )
        embed.add_field(
            name="✅ /還牌 紀錄id",
            value="標記某筆借牌紀錄已歸還\n例：`/還牌 5`",
            inline=False,
        )
        embed.add_field(
            name="📥 /借進來的牌",
            value="查看你目前借了哪些人的牌（只有你看得到）",
            inline=False,
        )
        embed.add_field(
            name="📤 /借出去的牌",
            value="查看你借出去還沒還的牌（只有你看得到）",
            inline=False,
        )
        embed.add_field(
            name="🔍 /查借牌 @某人",
            value="查看你跟某人之間所有未還紀錄（只有你看得到）",
            inline=False,
        )
        embed.add_field(
            name="📋 /借牌總覽",
            value="顯示整個伺服器所有未還紀錄（所有人都看得到）",
            inline=False,
        )
        embed.add_field(
            name="🔔 /提醒設定 開啟/關閉 [天數]",
            value="設定借牌超過幾天後自動 DM 提醒\n例：`/提醒設定 開啟 14`",
            inline=False,
        )
        embed.set_footer(text="ID 從 /借進來的牌 或 /借牌總覽 查詢")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Loans(bot))
