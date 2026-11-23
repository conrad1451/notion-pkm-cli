# utils/date_search.py

"""Interactive created/edited date search for Notion databases."""

from datetime import datetime, time, timezone
import click
from notion_client import APIResponseError

from client import notion, KEYS_EXPANDED
from utils.formatting import pick_from_list, browse_pages


DATE_MODES = [
    {"label": "Created date", "field": "created_time"},
    {"label": "Last edited date", "field": "last_edited_time"},
]

RANGE_MODES = [
    {"label": "On or after date", "op": "on_or_after"},
    {"label": "On or before date", "op": "on_or_before"},
    {"label": "Between two dates (inclusive)", "op": "between"},
]


def _local_tz():
    """Return the system's current local timezone (including DST rules)."""
    return datetime.now().astimezone().tzinfo


def _parse_date_to_iso(date_str: str, end_of_day: bool = False) -> str:
    """
    Convert a YYYY-MM-DD calendar date in the local timezone into an
    ISO-8601 UTC timestamp string for Notion queries.
    """
    parsed_date = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    boundary = time.max if end_of_day else time.min
    local_dt = datetime.combine(parsed_date, boundary, tzinfo=_local_tz())
    utc_dt = local_dt.astimezone(timezone.utc)
    return utc_dt.isoformat()

def prompt_basket_date_filter() -> dict | None:
    """Prompt the user for a created/edited date filter for the search basket."""
    date_choice = pick_from_list(
        DATE_MODES,
        label_fn=lambda item: item["label"],
        key_list="12",
        prompt="Filter by which date? ",
    )
    if not date_choice:
        return None

    range_choice = pick_from_list(
        RANGE_MODES,
        label_fn=lambda item: item["label"],
        key_list="123",
        prompt="Select date condition: ",
    )
    if not range_choice:
        return None

    field = date_choice["field"]
    op = range_choice["op"]
    short = "Created" if field == "created_time" else "Edited"

    try:
        if op == "on_or_after":
            start_str = click.prompt("On or after date (YYYY-MM-DD)").strip()
            start_iso = _parse_date_to_iso(start_str, end_of_day=False)
            condition = {"on_or_after": start_iso}
            display = f"{short} >= {start_str}"
        elif op == "on_or_before":
            end_str = click.prompt("On or before date (YYYY-MM-DD)").strip()
            end_iso = _parse_date_to_iso(end_str, end_of_day=True)
            condition = {"on_or_before": end_iso}
            display = f"{short} <= {end_str}"
        elif op == "between":
            start_str = click.prompt("Start date (YYYY-MM-DD)").strip()
            end_str = click.prompt("End date (YYYY-MM-DD)").strip()
            start_iso = _parse_date_to_iso(start_str, end_of_day=False)
            end_iso = _parse_date_to_iso(end_str, end_of_day=True)
            if start_iso > end_iso:
                raise ValueError("Start date must be on or before end date.")
            condition = {"on_or_after": start_iso, "on_or_before": end_iso}
            display = f"{short} between {start_str} and {end_str}"
        else:
            raise ValueError(f"Unsupported date operator: {op}")
    except ValueError as err:
        click.echo(f"❌ Invalid date input: {err}")
        return None

    return {
        "field": field,
        "op": op,
        "condition": condition,
        "display": display,
    }
    
def build_date_filter(
    field: str,
    op: str,
    start_date: str,
    end_date: str | None = None,
) -> dict:
    """Build a Notion API timestamp filter dictionary."""
    if op == "on_or_after":
        condition = {"on_or_after": _parse_date_to_iso(start_date, end_of_day=False)}
    elif op == "on_or_before":
        condition = {"on_or_before": _parse_date_to_iso(start_date, end_of_day=True)}
    elif op == "between":
        if not end_date:
            raise ValueError("End date is required for a date range.")
        start_iso = _parse_date_to_iso(start_date, end_of_day=False)
        end_iso = _parse_date_to_iso(end_date, end_of_day=True)
        if start_iso > end_iso:
            raise ValueError("Start date must be on or before end date.")
        condition = {
            "on_or_after": start_iso,
            "on_or_before": end_iso,
        }
    else:
        raise ValueError(f"Unsupported date operator: {op}")

    return {
        "timestamp": field,
        field: condition,
    }


def action_search_by_date(db: dict):
    """Prompt the user for date filter options and display matching pages."""
    date_choice = pick_from_list(
        DATE_MODES,
        label_fn=lambda item: item["label"],
        key_list="12",
        prompt="Filter by which date? ",
    )
    if not date_choice:
        return

    range_choice = pick_from_list(
        RANGE_MODES,
        label_fn=lambda item: item["label"],
        key_list="123",
        prompt="Select date condition: ",
    )
    if not range_choice:
        return

    try:
        if range_choice["op"] == "between":
            start_str = click.prompt("Start date (YYYY-MM-DD)")
            end_str = click.prompt("End date (YYYY-MM-DD)")
            notion_filter = build_date_filter(
                date_choice["field"], "between", start_str, end_str
            )
        else:
            target_str = click.prompt("Date (YYYY-MM-DD)")
            notion_filter = build_date_filter(
                date_choice["field"], range_choice["op"], target_str
            )
    except ValueError as err:
        click.echo(f"❌ Invalid date input: {err}")
        return

    click.echo(f"\n🔎 Filtering '{db['name']}' by {date_choice['label']}...")

    try:
        response = notion.databases.query(
            database_id=db["id"],
            filter=notion_filter,
            sorts=[{"timestamp": date_choice["field"], "direction": "descending"}],
        )
    except APIResponseError as err:
        click.echo(f"❌ Notion Query Error: {err}")
        return

    all_pages = response.get("results", [])
    pages = all_pages[: len(KEYS_EXPANDED)]

    if len(all_pages) > len(KEYS_EXPANDED):
        click.echo(f"⚠️  Showing first {len(KEYS_EXPANDED)} results only.")

    if not pages:
        click.echo("\nNo pages found matching that date filter.")
        return

    click.echo(f"\nFound {len(pages)} result(s):\n")
    browse_pages(pages)