"""The ``/playfix`` slash-command group (admins only)."""

from __future__ import annotations

import discord
from discord import app_commands

from .config import Mode


def _summary(cfg) -> str:
    state = "on" if cfg.enabled else "off"
    return (
        f"**PlayFix** is **{state}** here.\n"
        f"• Mode: `{cfg.mode}`"
        + (
            " (repost as the author, delete original)"
            if cfg.mode == "webhook"
            else " (reply with fixed links)"
        )
        + f"\n• Delete original: `{cfg.delete_original}`"
        f"\n• Disabled channels: `{len(cfg.disabled_channels)}`"
    )


class PlayFixCommands(app_commands.Group):
    """Admin configuration for PlayFix, scoped per guild."""

    def __init__(self, bot: discord.Client) -> None:
        super().__init__(
            name="playfix",
            description="Configure PlayFix",
            guild_only=True,
            default_permissions=discord.Permissions(manage_guild=True),
        )
        self.bot = bot

    @app_commands.command(description="Show PlayFix's current settings here")
    async def status(self, interaction: discord.Interaction) -> None:
        cfg = await self.bot.db.get(interaction.guild_id)  # type: ignore[attr-defined]
        await interaction.response.send_message(_summary(cfg), ephemeral=True)

    @app_commands.command(description="Turn PlayFix on in this server")
    async def enable(self, interaction: discord.Interaction) -> None:
        await self.bot.db.set_enabled(interaction.guild_id, True)  # type: ignore[attr-defined]
        await interaction.response.send_message("✅ PlayFix enabled.", ephemeral=True)

    @app_commands.command(description="Turn PlayFix off in this server")
    async def disable(self, interaction: discord.Interaction) -> None:
        await self.bot.db.set_enabled(interaction.guild_id, False)  # type: ignore[attr-defined]
        await interaction.response.send_message("🛑 PlayFix disabled.", ephemeral=True)

    @app_commands.command(description="Choose how fixed links are posted")
    @app_commands.describe(
        mode="webhook = post as the author (deletes original); reply = safe fallback"
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="webhook (post as author)", value="webhook"),
            app_commands.Choice(name="reply (non-destructive)", value="reply"),
        ]
    )
    async def mode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        value: Mode = mode.value  # type: ignore[assignment]
        await self.bot.db.set_mode(interaction.guild_id, value)  # type: ignore[attr-defined]
        await interaction.response.send_message(f"✅ Mode set to `{value}`.", ephemeral=True)

    @app_commands.command(
        name="delete-original", description="Whether webhook mode deletes the original message"
    )
    async def delete_original(self, interaction: discord.Interaction, value: bool) -> None:
        await self.bot.db.set_delete_original(interaction.guild_id, value)  # type: ignore[attr-defined]
        await interaction.response.send_message(
            f"✅ Delete original set to `{value}`.", ephemeral=True
        )

    @app_commands.command(description="Enable or disable PlayFix in this channel")
    async def channel(self, interaction: discord.Interaction, enabled: bool) -> None:
        await self.bot.db.set_channel_enabled(  # type: ignore[attr-defined]
            interaction.guild_id, interaction.channel_id, enabled
        )
        word = "enabled" if enabled else "disabled"
        await interaction.response.send_message(
            f"✅ PlayFix {word} in this channel.", ephemeral=True
        )
