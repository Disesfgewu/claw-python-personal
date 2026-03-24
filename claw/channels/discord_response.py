"""Discord response container — passed from templates to the dispatcher."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

import discord

if TYPE_CHECKING:
    pass


@dataclass
class DiscordResponse:
    """
    Unified container for everything a Discord template wants to send.

    The dispatcher (`DiscordChannel._dispatch`) reads this and calls
    the appropriate Discord API methods.
    """
    # Rich embeds (cards)
    embeds: list[discord.Embed] = field(default_factory=list)

    # Chart image as PNG bytes; set embed.set_image("attachment://chart_filename")
    chart_bytes: Optional[bytes] = None
    chart_filename: str = "chart.png"

    # Interactive components (buttons, selects, pagination)
    view: Optional[discord.ui.View] = None

    # Emoji reactions to add to the bot's own message
    reactions: list[str] = field(default_factory=list)

    # Fallback plain text (used when embeds list is empty)
    text: str = ""

    # Additional files beyond the chart
    extra_files: list[discord.File] = field(default_factory=list)
