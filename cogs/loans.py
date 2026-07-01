import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import database as db


def _loan_list_embed(title: str, loans, colour=discord.Colour.blurple()) -> discord.Embed:
    embed = discord.Embed(title=title, colour=colour)
    if not loans:
        embed.description = "目前沒有紀錄 ✅"
        return embed
    for loan in loans:
        qty = f" x{loan['quantity']}" if loan['quantity'] > 1 else ""
        note = f"\n> {loan['note']}" if loan['note'] else ""
        date = loan['borrowed_at'][:10]
        embed.add_field(
            name=f"#{loan['id']}  {loan['card_name']}{qty}",
            value=f"📅 {date}{note}",
            inline=False,
        )
    return embed


class Loans(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _ensure_user(self, user: discord.User | discord.Member):
        await db.upsert_user(str(user.id), user.display_name)

    # ── /borrow ──────────────────────────────────────────────────────────────
    @app_commands.command(name="borrow", description="記錄你跟某人借了牌")
    @app_commands.describe(
        lender="牌的擁有者（你跟誰借）",
        card_name="卡名",
        edition="版本／版號（可選，例如 EN-001、Alpha）",
        quantity="數量（預設 1）",
        note="備註（可選）",
    )
    async def borrow(
        self,
        interaction: discord.Interaction,
        lender: discord.Member,
        card_name: str,
        edition: Optional[str] = None,
        quantity: Optional[int] = 1,
        note: Optional[str] = None,
    ):
        if lender.id == interaction.user.id:
            await interaction.response.send_message("不能跟自己借牌 😅", ephemeral=True)
            return
        if quantity < 1:
            await interaction.response.send_message("數量至少為 1", ephemeral=True)
            return

        await self._ensure_user(interaction.user)
        await self._ensure_user(lender)
        await db.add_loan(
            str(interaction.guild_id),
            str(lender.id),
            str(interaction.user.id),
            card_name.strip(),
            edition.strip() if edition else None,
            quantity,
            note,
        )
        qty_str = f" x{quantity}" if quantity > 1 else ""
        edition_str = f" [{edition}]" if edition else ""
        await interaction.response.send_message(
            f"✅ 已記錄：**{interaction.user.display_name}** 跟 **{lender.display_name}** 借了 **{card_name}{edition_str}{qty_str}**"
        )

    @borrow.autocomplete("card_name")
    async def card_autocomplete(self, interaction: discord.Interaction, current: str):
        cards = await db.get_card_autocomplete(current)
        return [app_commands.Choice(name=c, value=c) for c in cards]

    # ── /mylent ───────────────────────────────────────────────────────────────
    @app_commands.command(name="mylent", description="查看你借出去、還沒還的牌")
    async def mylent(self, interaction: discord.Interaction):
        await self._ensure_user(interaction.user)
        loans = await db.get_active_loans_by_lender(str(interaction.user.id))

        # group by borrower
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
                date = loan['borrowed_at'][:10]
                lines.append(f"`#{loan['id']}` {loan['card_name']}{edition}{qty} — {date}")
            embed.add_field(name=f"👤 {borrower}", value="\n".join(lines), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /myborrowed ───────────────────────────────────────────────────────────
    @app_commands.command(name="myborrowed", description="查看你借進來、還沒還的牌")
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
                date = loan['borrowed_at'][:10]
                lines.append(f"`#{loan['id']}` {loan['card_name']}{edition}{qty} — {date}")
            embed.add_field(name=f"👤 {lender}", value="\n".join(lines), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /check ────────────────────────────────────────────────────────────────
    @app_commands.command(name="check", description="查看你跟某人之間的借貸狀況")
    @app_commands.describe(user="要查詢的對象")
    async def check(self, interaction: discord.Interaction, user: discord.Member):
        await self._ensure_user(interaction.user)
        await self._ensure_user(user)
        loans = await db.get_loans_between(str(interaction.user.id), str(user.id))

        embed = discord.Embed(
            title=f"🔍 你與 {user.display_name} 的借牌紀錄",
            colour=discord.Colour.green(),
        )
        if not loans:
            embed.description = "目前沒有未還紀錄 ✅"
        else:
            for loan in loans:
                qty = f" x{loan['quantity']}" if loan['quantity'] > 1 else ""
                edition = f" [{loan['edition']}]" if loan['edition'] else ""
                date = loan['borrowed_at'][:10]
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

    # ── /return ───────────────────────────────────────────────────────────────
    @app_commands.command(name="return", description="標記牌已歸還（用借牌紀錄的 ID）")
    @app_commands.describe(loan_id="借牌紀錄 ID（從 /myborrowed 查詢）")
    async def return_card(self, interaction: discord.Interaction, loan_id: int):
        success = await db.return_loan(loan_id, str(interaction.user.id))
        if success:
            await interaction.response.send_message(f"✅ 紀錄 #{loan_id} 已標記為歸還")
        else:
            await interaction.response.send_message(
                f"找不到 #{loan_id}，或這筆紀錄不是你借的", ephemeral=True
            )

    # ── /loans ────────────────────────────────────────────────────────────────
    @app_commands.command(name="loans", description="顯示伺服器所有未還紀錄（公開）")
    async def loans(self, interaction: discord.Interaction):
        all_loans = await db.get_all_active_loans(str(interaction.guild_id))
        if not all_loans:
            await interaction.response.send_message("伺服器目前沒有任何未還紀錄 ✅")
            return

        # group by borrower
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
                date = loan['borrowed_at'][:10]
                lines.append(
                    f"`#{loan['id']}` {loan['card_name']}{edition}{qty} ← **{loan['lender_name']}** · {date}"
                )
            embed.add_field(name=f"👤 {borrower}", value="\n".join(lines), inline=False)

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Loans(bot))
