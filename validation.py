import psycopg2
from lxml import etree

PG_DSN = "dbname=ragdb user=raguser host=localhost password=ragpass"

def normalize_profile(p):
    return "TZ" if not p or p.strip() == "" else p.strip()

def xml_keys(xml_path):
    tree = etree.parse(xml_path)
    root = tree.getroot()

    keys = set()
    for mpu in root.findall(".//MPU"):
        mpu_name = mpu.get("name")
        for prtn in mpu.findall(".//PRTn"):
            rg = int(prtn.get("index"))
            profile = normalize_profile(prtn.get("profile"))
            start = prtn.get("start")
            end = prtn.get("end")
            keys.add((mpu_name, rg, profile, start, end))
    return keys

def db_keys(project):
    conn = psycopg2.connect(PG_DSN)
    cur = conn.cursor()
    cur.execute("""
        SELECT mpu_name, rg_index, profile, start_hex, end_hex
        FROM policy_chunks
        WHERE project = %s
          AND is_active = true
    """, (project,))
    rows = cur.fetchall()
    conn.close()
    return set(rows)

if __name__ == "__main__":
    project = "KAANAPALLI"
    xml_path = "policies/KAANAPALLI/Access_control_v5.3.xml"

    xml_set = xml_keys(xml_path)
    db_set = db_keys(project)

    print("XML active policies :", len(xml_set))
    print("DB  active policies :", len(db_set))

    missing_in_db = xml_set - db_set
    extra_in_db   = db_set - xml_set

    print("\nIn XML but NOT in DB (missing):", len(missing_in_db))
    for k in list(missing_in_db)[:20]:
        print("  ", k)

    print("\nIn DB but NOT in XML (stale/extra):", len(extra_in_db))
    for k in list(extra_in_db)[:20]:
        print("  ", k)