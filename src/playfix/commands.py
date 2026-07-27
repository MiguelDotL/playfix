"""The ``/playfix`` slash-command group — server admins configure PlayFix here."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from .db import GuildConfig

if TYPE_CHECKING:
    from .bot import PlayFix


def _guild_id(interaction: discord.Interaction) -> int:
    # Every command in this group is guild_only, so this is always set.
    assert interaction.guild_id is not None
    return interaction.guild_id


def _describe(cfg: GuildConfig) -> str:
    state = "on" if cfg.enabled else "off"
    behaviour = (
        "repost as the author, delete the original"
        if cfg.mode == "webhook"
        else "reply with the fixed links"
    )
    return (
        f"**PlayFix** is **{state}** in this server.\n"
        f"• Mode: `{cfg.mode}` ({behaviour})\n"
        f"• Delete original: `{cfg.delete_original}`\n"
        f"• Channels disabled: `{len(cfg.disabled_channels)}`"
    )


class PlayFixCommands(app_commands.Group):
    """Admin-only configuration for PlayFix, scoped to one server."""

    def __init__(self, bot: PlayFix) -> None:
        super().__init__(
            name="playfix",
            description="Configure PlayFix",
            guild_only=True,
            default_permissions=discord.Permissions(manage_guild=True),
        )
        self.bot = bot

    @app_commands.command(description="Show PlayFix's settings in this server")
    async def status(self, interaction: discord.Interaction) -> None:
        cfg = await self.bot.db.get(_guild_id(interaction))
        await interaction.response.send_message(_describe(cfg), ephemeral=True)

    @app_commands.command(description="Turn PlayFix on in this server")
    async def enable(self, interaction: discord.Interaction) -> None:
        await self.bot.db.set_enabled(_guild_id(interaction), True)
        await interaction.response.send_message("✅ PlayFix enabled.", ephemeral=True)

    @app_commands.command(description="Turn PlayFix off in this server")
    async def disable(self, interaction: discord.Interaction) -> None:
        await self.bot.db.set_enabled(_guild_id(interaction), False)
        await interaction.response.send_message("🛑 PlayFix disabled.", ephemeral=True)

    @app_commands.command(description="Choose how fixed links are posted")
    @app_commands.describe(mode="How PlayFix posts the fixed link")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="webhook — post as the author", value="webhook"),
            app_commands.Choice(name="reply — non-destructive", value="reply"),
        ]
    )
    async def mode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        await self.bot.db.set_mode(_guild_id(interaction), mode.value)
        await interaction.response.send_message(f"✅ Mode set to `{mode.value}`.", ephemeral=True)

    @app_commands.command(
        name="delete-original",
        description="Whether webhook mode deletes the original message",
    )
    async def delete_original(self, interaction: discord.Interaction, value: bool) -> None:
        await self.bot.db.set_delete_original(_guild_id(interaction), value)
        await interaction.response.send_message(
            f"✅ Delete original set to `{value}`.", ephemeral=True
        )

    @app_commands.command(description="Enable or disable PlayFix in this channel")
    async def channel(self, interaction: discord.Interaction, enabled: bool) -> None:
        assert interaction.channel_id is not None
        await self.bot.db.set_channel_enabled(
            _guild_id(interaction), interaction.channel_id, enabled
        )
        word = "enabled" if enabled else "disabled"
        await interaction.response.send_message(
            f"✅ PlayFix {word} in this channel.", ephemeral=True
        )
