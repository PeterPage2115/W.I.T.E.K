"""In-game URL deep link generators for Travian Legends.

URLs open the corresponding game page when clicked by a logged-in player.
Designed for use in Discord embed fields.
"""


def map_link(server_url: str, x: int, y: int) -> str:
    """Link to map tile position details."""
    base = server_url.rstrip("/")
    return f"{base}/position_details.php?x={x}&y={y}"


def send_troops_link(
    server_url: str, x: int, y: int,
    event_type: int = 2, troops: dict[str, int] | None = None,
) -> str:
    """Link to send troops form.

    event_type: 2=reinforce, 3=attack, 4=raid
    troops: optional dict of troop slot → count
    """
    base = server_url.rstrip("/")
    url = f"{base}/build.php?id=39&tt=2&x={x}&y={y}&eventType={event_type}"
    if troops:
        for unit_key, count in troops.items():
            url += f"&troop[{unit_key}]={count}"
    return url


def marketplace_link(server_url: str, x: int, y: int) -> str:
    """Link to marketplace send resources form."""
    base = server_url.rstrip("/")
    return f"{base}/build.php?gid=17&x={x}&y={y}&t=5"


def format_coord_with_link(server_url: str, x: int, y: int) -> str:
    """Format coordinates as a clickable markdown link for Discord embeds.

    Returns: '[📍 (50|-30)](https://server/position_details.php?x=50&y=-30)'
    """
    url = map_link(server_url, x, y)
    return f"[📍 ({x}|{y})]({url})"
