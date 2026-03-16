"""Ingest package — data pipeline tooling for Barbooks AI.

Re-exports the public API from ingest.cli for backward compatibility.
"""

from ingest.cli import (  # noqa: F401
    _clean_name,
    _extract_answer_count,
    _extract_title,
    _find_xlsx,
    _parse_ordered_list_items,
    _parse_table_items,
    _write_page_to_spreadsheet,
    parse_page_data,
)
