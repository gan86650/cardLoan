import discord
from discord import app_commands
from discord.ext import commands, tasks
from collections import defaultdict
import database as db


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_reminder.start()

    def cog_unload(self):
        self.daily_reminder.cancel()

    # ── 每天跑一次提醒 ────────────────────────────────────────────────────────
    @tasks.loop(hours=24)
    async def daily_reminder(self):
        overdue = await db.get_overdue_loans(days=0)  # days filter is per-user in SQL

        # group by borrower
        by_borrower: dict[str, list] = defaultdict(list)
        for loan in overdue:
            by_borrower[loan["borrower_id"]].append(loan)

        for borrower_id, loans in by_borrower.items():
            user = self.bot.get_user(int(borrower_id))
            if user is None:
                try:
                    user = await self.bot.fetch_user(int(borrower_id))
                except Exception:
                    continue

            lines = []
            for loan in loans:
                qty = f" x{loan['quantity']}" if loan['quantity'] > 1 else ""
                date = loan['borrowed_at'][:10]
                days_ago = int(loan["reminder_days"])
                lines.append(
                    f"• `#{loan['id']}` **{loan['card_name']}{qty}** "
                    f"← {loan['lender_name']} （借了 {days_ago}+ 天，從 {date}）"
                )

            embed = discord.Embed(
                title="🔔 借牌提醒",
                description=(
                    "你有以下牌還沒還，記得跟牌主確認一下！\n\n"
                    + "\n".join(lines)
                    + "\n\n還牌後用 `/return <ID>` 標記歸還。"
                ),
                colour=discord.Colour.yellow(),
            )
            try:
                await user.send(embed=embed)
            except discord.Forbidden:
                pass  # DM 被關掉，略過

    @daily_reminder.before_loop
    async def before_reminder(self):
        await self.bot.wait_until_ready()

    # ── /reminder ─────────────────────────────────────────────────────────────
    @app_commands.command(name="reminder", description="設定借牌到期提醒")
    @app_commands.describe(
        enabled="開啟或關閉提醒",
        days="借牌超過幾天後提醒（預設 7）",
    )
    @app_commands.choices(enabled=[
        app_commands.Choice(name="開啟", value=1),
        app_commands.Choice(name="關閉", value=0),
    ])
    async def reminder(
        self,
        interaction: discord.Interaction,
        enabled: app_commands.Choice[int],
        days: int = None,
    ):
        await db.upsert_user(str(interaction.user.id), interaction.user.display_name)

        if days is not None and days < 1:
            await interaction.response.send_message("天數至少為 1", ephemeral=True)
            return

        await db.set_reminder(str(interaction.user.id), bool(enabled.value), days)

        if enabled.value:
            day_str = f"{days} 天" if days else "你原本設定的天數"
            await interaction.response.send_message(
                f"🔔 提醒已**開啟**，借牌超過 {day_str} 後會 DM 你", ephemeral=True
            )
        else:
            await interaction.response.send_message("🔕 提醒已**關閉**", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Reminders(bot))
