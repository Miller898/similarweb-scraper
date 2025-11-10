import json
import logging
import os
from typing import Any, Dict, Iterable, List

import pandas as pd

logger = logging.getLogger(__name__)

def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

def _flatten_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten nested fields for CSV/XLSX export. Complex structures
    are stored as JSON strings.
    """
    flattened: Dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, (dict, list)):
            flattened[key] = json.dumps(value, ensure_ascii=False)
        else:
            flattened[key] = value
    return flattened

def export_data(
    records: Iterable[Dict[str, Any]],
    output_format: str,
    output_path: str,
) -> None:
    """
    Export analytics records to JSON, CSV, or Excel.
    """
    output_format = output_format.lower()
    records_list: List[Dict[str, Any]] = list(records)
    if not records_list:
        raise ValueError("No records to export")

    _ensure_parent_dir(output_path)
    logger.info(
        "Exporting %d records to %s (%s)",
        len(records_list),
        output_path,
        output_format,
    )

    if output_format == "json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(records_list, f, ensure_ascii=False, indent=2)
        return

    flattened = [_flatten_record(r) for r in records_list]
    df = pd.DataFrame(flattened)

    if output_format == "csv":
        df.to_csv(output_path, index=False)
    elif output_format == "xlsx":
        df.to_excel(output_path, index=False)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")