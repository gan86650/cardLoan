import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import database as db


class QuantityModal(discord.ui.Modal, title="修改數量"):
    數量 = discord.ui.TextInput(label="數量", placeholder="請輸入新的數量", max_length=5)

    def __init__(self, view: "BorrowConfirmView | LendConfirmView | ReturnConfirmView"):
        super().__init__()
        self.view_ref = view
        self.數量.default = str(view.quantity)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.數量.value.strip()
        if not raw.isdigit() or int(raw) < 1:
            await interaction.response.send_message("數量必須是大於 0 的整數", ephemeral=True)
            return

        new_qty = int(raw)
        max_qty = getattr(self.view_ref, "max_quantity", None)
        if max_qty is not None and new_qty > max_qty:
            await interaction.response.send_message(
                f"數量不可超過剩餘的 {max_qty} 張", ephemeral=True
            )
            return

        self.view_ref.quantity = new_qty
        await interaction.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)


class BorrowConfirmView(discord.ui.View):
    def __init__(
        self,
        cog: "Loans",
        borrower: discord.Member,
        lender: discord.Member,
        card_name: str,
        edition: Optional[str],
        quantity: int,
        note: Optional[str],
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.borrower = borrower
        self.lender = lender
        self.card_name = card_name
        self.edition = edition
        self.quantity = quantity
        self.note = note
        self.message: Optional[discord.Message] = None

    def build_embed(self) -> discord.Embed:
        qty_str = f" x{self.quantity}" if self.quantity > 1 else ""
        edition_str = f" [{self.edition}]" if self.edition else ""
        embed = discord.Embed(
            title="📋 請確認借牌資訊",
            description=(
                f"**{self.borrower.display_name}** 跟 **{self.lender.display_name}** 借了\n"
                f"**{self.card_name}{edition_str}{qty_str}**"
            ),
            colour=discord.Colour.yellow(),
        )
        if self.note:
            embed.add_field(name="備註", value=self.note, inline=False)
        embed.set_footer(text="請確認資訊是否正確")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.borrower.id:
            await interaction.response.send_message(
                "只有發起指令的人可以操作這則確認訊息", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⌛ 確認逾時，若要記錄請重新輸入指令", embed=None, view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="✅ 確認", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._ensure_user(self.borrower)
        await self.cog._ensure_user(self.lender)
        await db.add_loan(
            str(interaction.guild_id),
            str(self.lender.id),
            str(self.borrower.id),
            self.card_name,
            self.edition,
            self.quantity,
            self.note,
        )
        qty_str = f" x{self.quantity}" if self.quantity > 1 else ""
        edition_str = f" [{self.edition}]" if self.edition else ""
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"✅ 已記錄：**{self.borrower.display_name}** 跟 **{self.lender.display_name}** 借了 **{self.card_name}{edition_str}{qty_str}**",
            embed=None,
            view=None,
        )
        self.stop()

    @discord.ui.button(label="✏️ 修改數量", style=discord.ButtonStyle.blurple)
    async def edit_quantity(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(QuantityModal(self))

    @discord.ui.button(label="❌ 取消", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ 已取消", embed=None, view=None)
        self.stop()


class LendConfirmView(discord.ui.View):
    def __init__(
        self,
        cog: "Loans",
        lender: discord.Member,
        borrower: discord.Member,
        card_name: str,
        edition: Optional[str],
        quantity: int,
        note: Optional[str],
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.lender = lender
        self.borrower = borrower
        self.card_name = card_name
        self.edition = edition
        self.quantity = quantity
        self.note = note
        self.message: Optional[discord.Message] = None

    def build_embed(self) -> discord.Embed:
        qty_str = f" x{self.quantity}" if self.quantity > 1 else ""
        edition_str = f" [{self.edition}]" if self.edition else ""
        embed = discord.Embed(
            title="📋 請確認借出資訊",
            description=(
                f"**{self.lender.display_name}** 借給 **{self.borrower.display_name}**\n"
                f"**{self.card_name}{edition_str}{qty_str}**"
            ),
            colour=discord.Colour.yellow(),
        )
        if self.note:
            embed.add_field(name="備註", value=self.note, inline=False)
        embed.set_footer(text="請確認資訊是否正確")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.lender.id:
            await interaction.response.send_message(
                "只有發起指令的人可以操作這則確認訊息", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⌛ 確認逾時，若要記錄請重新輸入指令", embed=None, view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="✅ 確認", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._ensure_user(self.lender)
        await self.cog._ensure_user(self.borrower)
        await db.add_loan(
            str(interaction.guild_id),
            str(self.lender.id),
            str(self.borrower.id),
            self.card_name,
            self.edition,
            self.quantity,
            self.note,
        )
        qty_str = f" x{self.quantity}" if self.quantity > 1 else ""
        edition_str = f" [{self.edition}]" if self.edition else ""
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"✅ 已記錄：**{self.lender.display_name}** 借給 **{self.borrower.display_name}** **{self.card_name}{edition_str}{qty_str}**",
            embed=None,
            view=None,
        )
        self.stop()

    @discord.ui.button(label="✏️ 修改數量", style=discord.ButtonStyle.blurple)
    async def edit_quantity(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(QuantityModal(self))

    @discord.ui.button(label="❌ 取消", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ 已取消", embed=None, view=None)
        self.stop()


class ReturnConfirmView(discord.ui.View):
    def __init__(
        self,
        borrower_id: int,
        loan_id: int,
        card_name: str,
        edition: Optional[str],
        quantity: int,
        max_quantity: int,
        lender_name: str,
    ):
        super().__init__(timeout=120)
        self.borrower_id = borrower_id
        self.loan_id = loan_id
        self.card_name = card_name
        self.edition = edition
        self.quantity = quantity
        self.max_quantity = max_quantity
        self.lender_name = lender_name
        self.message: Optional[discord.Message] = None

    def build_embed(self) -> discord.Embed:
        qty_str = f" x{self.quantity}" if self.quantity > 1 else ""
        edition_str = f" [{self.edition}]" if self.edition else ""
        embed = discord.Embed(
            title="📋 請確認還牌資訊",
            description=(
                f"紀錄 `#{self.loan_id}`：**{self.card_name}{edition_str}{qty_str}**\n"
                f"跟 **{self.lender_name}** 借的，目前尚有 {self.max_quantity} 張未還"
            ),
            colour=discord.Colour.yellow(),
        )
        embed.set_footer(text="請確認歸還數量是否正確")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.borrower_id:
            await interaction.response.send_message(
                "只有發起指令的人可以操作這則確認訊息", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⌛ 確認逾時，若要歸還請重新輸入指令", embed=None, view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="✅ 確認", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = await db.return_loan(self.loan_id, str(self.borrower_id), self.quantity)
        for item in self.children:
            item.disabled = True

        if result is None:
            await interaction.response.edit_message(
                content=f"⚠️ 找不到紀錄 #{self.loan_id}，可能已被歸還或刪除",
                embed=None,
                view=None,
            )
            self.stop()
            return

        edition_str = f" [{result['edition']}]" if result["edition"] else ""
        if result["fully_returned"]:
            content = (
                f"✅ 紀錄 #{self.loan_id} {result['card_name']}{edition_str} "
                f"已全部歸還（{result['returned_qty']} 張）"
            )
        else:
            content = (
                f"✅ 紀錄 #{self.loan_id} {result['card_name']}{edition_str} "
                f"已歸還 {result['returned_qty']} 張，剩餘 {result['remaining_qty']} 張未還"
            )
        await interaction.response.edit_message(content=content, embed=None, view=None)
        self.stop()

    @discord.ui.button(label="✏️ 修改數量", style=discord.ButtonStyle.blurple)
    async def edit_quantity(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(QuantityModal(self))

    @discord.ui.button(label="❌ 取消", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ 已取消", embed=None, view=None)
        self.stop()


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

        view = BorrowConfirmView(
            self,
            interaction.user,
            牌主,
            卡名.strip(),
            版本.strip() if 版本 else None,
            數量,
            備註,
        )
        await interaction.response.send_message(embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()

    @borrow.autocomplete("卡名")
    async def card_autocomplete(self, interaction: discord.Interaction, current: str):
        cards = await db.get_card_autocomplete(current)
        return [app_commands.Choice(name=c, value=c) for c in cards]

    # ── /借出 ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="借出", description="記錄你借出牌給某人")
    @app_commands.describe(
        借用人="跟你借牌的人",
        卡名="卡名",
        版本="版本／版號（可選，例如 EN-001、Alpha）",
        數量="數量（預設 1）",
        備註="備註（可選）",
    )
    async def lend(
        self,
        interaction: discord.Interaction,
        借用人: discord.Member,
        卡名: str,
        版本: Optional[str] = None,
        數量: Optional[int] = 1,
        備註: Optional[str] = None,
    ):
        if 借用人.id == interaction.user.id:
            await interaction.response.send_message("不能借給自己 😅", ephemeral=True)
            return
        if 數量 < 1:
            await interaction.response.send_message("數量至少為 1", ephemeral=True)
            return

        view = LendConfirmView(
            self,
            interaction.user,
            借用人,
            卡名.strip(),
            版本.strip() if 版本 else None,
            數量,
            備註,
        )
        await interaction.response.send_message(embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()

    @lend.autocomplete("卡名")
    async def lend_card_autocomplete(self, interaction: discord.Interaction, current: str):
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
    @app_commands.command(name="還牌", description="標記牌已歸還（用借牌紀錄的 ID，可指定數量做部分歸還）")
    @app_commands.describe(
        紀錄id="借牌紀錄 ID（從 /借進來的牌 查詢）",
        數量="要歸還的數量（預設為全部歸還）",
    )
    async def return_card(
        self,
        interaction: discord.Interaction,
        紀錄id: int,
        數量: Optional[int] = None,
    ):
        if 數量 is not None and 數量 < 1:
            await interaction.response.send_message("數量至少為 1", ephemeral=True)
            return

        loan = await db.get_loan(紀錄id, str(interaction.user.id))
        if loan is None:
            await interaction.response.send_message(
                f"找不到 #{紀錄id}，或這筆紀錄不是你借的", ephemeral=True
            )
            return

        max_qty = loan["quantity"]
        quantity = 數量 if 數量 is not None else max_qty
        if quantity > max_qty:
            await interaction.response.send_message(
                f"數量不可超過剩餘的 {max_qty} 張", ephemeral=True
            )
            return

        view = ReturnConfirmView(
            interaction.user.id,
            紀錄id,
            loan["card_name"],
            loan["edition"],
            quantity,
            max_qty,
            loan["lender_name"],
        )
        await interaction.response.send_message(embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()

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
            name="📤 /借出 @借用人 卡名 [版本] [數量] [備註]",
            value="記錄你借出牌給某人\n例：`/借出 @小明 Robogon of Starfall Ridge EN-001 2`",
            inline=False,
        )
        embed.add_field(
            name="✅ /還牌 紀錄id [數量]",
            value="標記某筆借牌紀錄已歸還，可指定數量做部分歸還（省略則全部歸還）\n例：`/還牌 5` 或 `/還牌 5 2`",
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
