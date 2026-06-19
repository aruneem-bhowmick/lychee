"""Authorization logic for gating @lychee command execution.

Checks whether a GitHub user is permitted to trigger commands based on
the ``authorization.allowed_users`` config list.  When the list is empty
every user is permitted (open access).  Comparisons are case-insensitive
because GitHub treats logins as case-insensitive identifiers.

This module is pure logic — it performs no I/O and does not call the
GitHub API.  The caller is responsible for posting any refusal message.
"""

from __future__ import annotations

import logging

from lychee.config import LycheeConfig

_logger = logging.getLogger(__name__)

REFUSAL_MARKER: str = "<!-- lychee:command-refused -->"
"""Hidden marker embedded in refusal comments for identification and dedup."""


def is_authorized(user: str, config: LycheeConfig) -> bool:
    """Check if a GitHub user is authorized to trigger commands.

    Returns ``True`` if:
    - ``config.authorization.allowed_users`` is empty (open access), OR
    - *user* (case-insensitive) is in ``config.authorization.allowed_users``.

    GitHub logins are compared case-insensitively because GitHub
    treats logins as case-insensitive.
    """
    allowed = config.authorization.allowed_users
    if not allowed:
        return True

    normalized_user = user.strip().lower()
    allowed_set = {u.strip().lower() for u in allowed}

    authorized = normalized_user in allowed_set
    if not authorized:
        _logger.info("User %r denied: not in allowed_users list", user)
    return authorized


def format_refusal(user: str) -> str:
    """Format the refusal message for an unauthorized user.

    Returns a markdown string suitable for posting as an issue comment.
    The message is clear and non-hostile, explaining that the user is not
    on the authorized list without revealing the list itself.
    """
    return (
        f"{REFUSAL_MARKER}\n"
        f"Hi @{user}, you're not on the authorized list for `@lychee` "
        f"commands in this repository. A maintainer can add you to "
        f"`authorization.allowed_users` in `.lychee.yml`."
    )
