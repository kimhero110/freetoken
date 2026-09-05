import sqlite3
import os
import shutil

db = "/opt/npm/data/database.sqlite"
conn = sqlite3.connect(db)
c = conn.cursor()

# 1. Install cert into NPM custom_ssl/npm-3
cert_dir = "/opt/npm/data/custom_ssl/npm-3"
os.makedirs(cert_dir, exist_ok=True)
shutil.copy2("/root/.acme.sh/test.witkit.zone_ecc/fullchain.cer", f"{cert_dir}/fullchain.pem")
shutil.copy2("/root/.acme.sh/test.witkit.zone_ecc/test.witkit.zone.key", f"{cert_dir}/privkey.pem")

# Check or insert certificate record
c.execute("SELECT id FROM certificate WHERE nice_name = ?", ("test.witkit.zone",))
row = c.fetchone()
if row:
    cert_id = row[0]
else:
    c.execute("""INSERT INTO certificate 
      (created_on, modified_on, owner_user_id, is_deleted, provider, nice_name, domain_names, expires_on, meta)
      VALUES (datetime('now'), datetime('now'), 1, 0, 'other', 'test.witkit.zone', '["test.witkit.zone"]', datetime('now', '+90 days'), '{}')""")
    cert_id = c.lastrowid

# 2. Add or update proxy host for test.witkit.zone
c.execute("SELECT id FROM proxy_host WHERE domain_names LIKE ?", ("%test.witkit.zone%",))
p_row = c.fetchone()
if p_row:
    host_id = p_row[0]
    c.execute("""UPDATE proxy_host SET 
      forward_host = '100.64.0.17', forward_port = 8500, forward_scheme = 'http',
      certificate_id = ?, ssl_forced = 1, http2_support = 1, allow_websocket_upgrade = 1, enabled = 1
      WHERE id = ?""", (cert_id, host_id))
else:
    c.execute("""INSERT INTO proxy_host 
      (created_on, modified_on, owner_user_id, is_deleted, domain_names, forward_host, forward_port, 
       access_list_id, certificate_id, ssl_forced, caching_enabled, block_exploits, advanced_config, 
       meta, allow_websocket_upgrade, http2_support, forward_scheme, enabled, locations, hsts_enabled, 
       hsts_subdomains, trust_forwarded_proto)
      VALUES (datetime('now'), datetime('now'), 1, 0, '["test.witkit.zone"]', '100.64.0.17', 8500,
       0, ?, 1, 0, 1, '', '{}', 1, 1, 'http', 1, '[]', 1, 0, 1)""", (cert_id,))
    host_id = c.lastrowid

conn.commit()
conn.close()

# 3. Generate nginx config file /opt/npm/data/nginx/proxy_host/{host_id}.conf
conf_path = f"/opt/npm/data/nginx/proxy_host/{host_id}.conf"
nginx_conf = f"""# ------------------------------------------------------------
# test.witkit.zone
# ------------------------------------------------------------

server {{
  set $forward_scheme http;
  set $server         "100.64.0.17";
  set $port           8500;

  listen 80;
  listen [::]:80;

  listen 443 ssl http2;
  listen [::]:443 ssl http2;

  server_name test.witkit.zone;

  # Custom SSL Certificate
  ssl_certificate /data/custom_ssl/npm-3/fullchain.pem;
  ssl_certificate_key /data/custom_ssl/npm-3/privkey.pem;

  # HSTS
  add_header Strict-Transport-Security "max-age=63072000; preload" always;

  # Force SSL
  if ($scheme = "http") {{
    return 301 https://$host$request_uri;
  }}

  # Block Exploits
  include conf.d/include/block-exploits.conf;

  access_log /data/logs/proxy-host-{host_id}_access.log proxy;
  error_log /data/logs/proxy-host-{host_id}_error.log warn;

  location / {{
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
    proxy_http_version 1.1;

    # Proxy parameters
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_pass http://100.64.0.17:8500;
  }}
}}
"""
with open(conf_path, "w", encoding="utf-8") as f:
    f.write(nginx_conf)

print(f"SUCCESS: Configured NPM host {host_id} for test.witkit.zone")
