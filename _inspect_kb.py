# -*- coding: utf-8 -*-
# Temporary read-only inspector: enumerate KBs and chunk provenance (no writes).
import json
import sqlite3

con = sqlite3.connect("file:D:/projects/lingshu/backend/data/app.db?mode=ro", uri=True)
cur = con.cursor()

kbs = cur.execute(
    "select id,name,space_id,chunk_size,status from knowledge_bases order by id"
).fetchall()
print("KBS=" + json.dumps(kbs, ensure_ascii=True))

chunks = cur.execute(
    "select kb_id, content, meta from knowledge_chunks order by kb_id, id"
).fetchall()
agg = {}
for kb_id, content, meta in chunks:
    m = json.loads(meta or "{}")
    key = (kb_id, m.get("filename", "?"))
    e = agg.setdefault(
        key, {"kb": kb_id, "file": m.get("filename", "?"), "chunks": 0, "chars": 0}
    )
    e["chunks"] += 1
    e["chars"] += len(content or "")

print("PER_DOC=" + json.dumps(list(agg.values()), ensure_ascii=True, indent=1))
print("TOTAL_CHUNKS=" + str(len(chunks)))
con.close()
