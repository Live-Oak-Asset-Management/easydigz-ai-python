import os
import subprocess
import pymysql
from datetime import datetime
from urllib.parse import urlparse

# === DB CONFIGURATION ===
DB_CONFIG = {
    'host': 'stage-cle-ezd-noco-retool.cktfz7cqhztl.us-east-1.rds.amazonaws.com',
    'database': 'EasyDigz',
    'user': 'admin',
    'password': 'Sample!12345:asasa',
    'port': 3306
}

BACKUP_DIR = './backups'
TABLE_NAME = 'domain_agent_mapping'

# === DOMAIN & INSERT DATA ===
input_domain = "https://custom.ideafoundation.in"
agent_id = "107649577889983698871"
is_active = 1

# === STEP 1: Clean Domain ===
def clean_domain(url):
    parsed = urlparse(url)
    return parsed.netloc if parsed.netloc else parsed.path

domain = clean_domain(input_domain)

# === STEP 2: Backup Specific Table ===
def backup_table():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{DB_CONFIG['database']}_{timestamp}.sql"
    filepath = os.path.join(BACKUP_DIR, filename)
    os.makedirs(BACKUP_DIR, exist_ok=True)

    cmd = [
        'mysqldump',
        f"-h{DB_CONFIG['host']}",
        f"-P{DB_CONFIG['port']}",
        f"-u{DB_CONFIG['user']}",
        f"-p{DB_CONFIG['password']}",
        DB_CONFIG['database']
    ]

    with open(filepath, 'w') as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        raise Exception(f"❌ Backup failed: {result.stderr}")
    else:
        print(f"✅ Backup created at {filepath}")

# === STEP 3: Insert Mapping ===
def insert_mapping(domain, agent_id, is_active):
    conn = pymysql.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        database=DB_CONFIG['database'],
        port=DB_CONFIG['port']
    )

    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    insert_sql = f"""
        INSERT INTO {TABLE_NAME} (domain, agent_id, is_active, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s)
    """

    try:
        with conn.cursor() as cur:
            cur.execute(insert_sql, (domain, agent_id, is_active, now, now))
        conn.commit()
        print(f"✅ Mapping inserted: {domain} → {agent_id}")
    except Exception as e:
        print("❌ Failed to insert mapping:", e)
    finally:
        conn.close()


# ===  Delete Record (if exists) ===
def delete_mapping(domain):
    conn = pymysql.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        database=DB_CONFIG['database'],
        port=DB_CONFIG['port']
    )

    delete_sql = f"DELETE FROM {TABLE_NAME} WHERE domain = %s"

    try:
        with conn.cursor() as cur:
            rows = cur.execute(delete_sql, (domain,))
        conn.commit()
        if rows:
            print(f"🗑️ Deleted existing record(s) for domain: {domain}")
        else:
            print(f"ℹ️ No existing record found for domain: {domain}")
    except Exception as e:
        print("❌ Failed to delete mapping:", e)
    finally:
        conn.close()

# === MAIN ===
if __name__ == "__main__":
    try:
        print(f"Preparing to insert mapping for domain: {domain}")
        # backup_table() use only when required
        # delete_mapping(domain)
        insert_mapping(domain, agent_id, is_active)
    except Exception as err:
        print("❌ Error:", err)
