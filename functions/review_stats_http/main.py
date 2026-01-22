import os
from datetime import datetime, timezone
from google.cloud import firestore

FIRESTORE_DB = os.environ.get("FIRESTORE_DB", "resturantdb2")
INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "")

db = firestore.Client(database=FIRESTORE_DB)

def review_stats_http(request):
    # Simple auth: require token header
    token = request.headers.get("X-Internal-Token", "")
    if INTERNAL_TOKEN and token != INTERNAL_TOKEN:
        return ("Unauthorized", 401)

    data = request.get_json(silent=True) or {}
    item_id = data.get("item_id")
    rating = data.get("rating")

    if item_id is None or rating is None:
        return ("Missing item_id or rating", 400)

    item_id = str(item_id)
    rating = float(rating)

    stats_ref = db.collection("item_stats").document(item_id)

    @firestore.transactional
    def txn_update(transaction):
        snap = stats_ref.get(transaction=transaction)
        existing = snap.to_dict() if snap.exists else {}

        count = int(existing.get("review_count", 0))
        total = float(existing.get("total_rating", 0.0))

        count += 1
        total += rating
        avg = round(total / count, 3)

        transaction.set(
            stats_ref,
            {
                "item_id": item_id,
                "review_count": count,
                "total_rating": total,
                "avg_rating": avg,
                "updated_at": datetime.now(timezone.utc),
            },
            merge=True,
        )

    txn_update(db.transaction())
    return ({"ok": True, "item_id": item_id}, 200)
