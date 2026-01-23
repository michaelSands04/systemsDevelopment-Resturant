import os
import io
import csv
import json
from datetime import datetime
from google.cloud import firestore

FIRESTORE_DB = os.environ.get("FIRESTORE_DB", "resturantdb2")
INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "")

db = firestore.Client(database=FIRESTORE_DB)

def _unauthorized():
    return ("Unauthorized", 401)

def export_reviews_http(request):
    # --- Token auth ---
    token = request.headers.get("X-Internal-Token", "")
    if INTERNAL_TOKEN and token != INTERNAL_TOKEN:
        return _unauthorized()

    # --- Params ---
    fmt = (request.args.get("format", "csv") or "csv").lower()  # csv | json
    item_id = request.args.get("item_id")  # optional
    limit_raw = request.args.get("limit", "100")

    try:
        limit = max(1, min(1000, int(limit_raw)))
    except ValueError:
        limit = 100

    # --- Build query (NO composite index required) ---
    col = db.collection("reviews")

    if item_id is not None:
        # IMPORTANT: Use ONLY a filter + limit (no order_by) -> avoids composite index requirement
        try:
            item_id_int = int(item_id)
        except ValueError:
            return (
                json.dumps({"error": "item_id must be an integer"}),
                400,
                {"Content-Type": "application/json"},
            )

        q = col.where("item_id", "==", item_id_int).limit(limit)
    else:
        # No filter: order_by is fine without a composite index
        q = col.order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)

    docs = q.stream()

    rows = []
    for d in docs:
        data = d.to_dict() or {}

        # Make timestamp safe + create sort key
        ts = data.get("created_at")
        if hasattr(ts, "isoformat"):
            iso = ts.isoformat()
        else:
            iso = ""

        data["created_at"] = iso
        data["_sort"] = iso  # for python-side sorting when filtered
        data["id"] = d.id

        rows.append(data)

    # If filtered, Firestore didn't order it -> sort in Python
    if item_id is not None:
        rows.sort(key=lambda r: r.get("_sort", ""), reverse=True)

    for r in rows:
        r.pop("_sort", None)

    # --- Output ---
    if fmt == "json":
        return (json.dumps(rows), 200, {"Content-Type": "application/json"})

    # CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "username", "item_id", "rating", "comment", "created_at"])

    for r in rows:
        writer.writerow([
            r.get("id", ""),
            r.get("username", ""),
            r.get("item_id", ""),
            r.get("rating", ""),
            r.get("comment", ""),
            r.get("created_at", ""),
        ])

    filename = f"reviews_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return (
        output.getvalue(),
        200,
        {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
