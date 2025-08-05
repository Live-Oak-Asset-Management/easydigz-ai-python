import subprocess
from pathlib import Path

def write_agent_nginx_conf(domain, agent_id, output_path=None):
    if not domain or not agent_id:
        raise ValueError("Both domain and agent_id are required.")

    if output_path is None:
        safe_name = domain.replace('.', '_')
        # output_path = f"/etc/nginx/conf.d/{safe_name}.conf"
        output_path = f"/home/idea/Desktop/scripts/{safe_name}.conf"

    conf = f"""
server {{

    listen 80;
    server_name {domain};
    proxy_set_header Host {agent_id}.easydigz.com;

    location ~ /api/auth/(.*) {{
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
    }}

    location /api {{
        proxy_pass http://localhost:7000/api;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
    }}

    location / {{
        proxy_pass http://localhost:3000;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_buffer_size 16k;
        proxy_buffers 4 32k;
        proxy_busy_buffers_size 64k;
    }}
}}
""".strip()

    # Write the config
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(conf)

    print(f" NGINX config created at: {output_path}")
    return output_path


def test_and_reload_nginx():
    # Test NGINX config syntax
    test = subprocess.run(["sudo", "nginx", "-t"], capture_output=True, text=True)
    if test.returncode == 0:
        print(" NGINX config is valid.")
        reload = subprocess.run(["sudo", "nginx", "-s", "reload"])
        if reload.returncode == 0:
            print(" NGINX successfully reloaded.")
        else:
            print("⚠️ Reload failed.")
    else:
        print(" NGINX config test failed:")
        print(test.stderr)


if __name__ == "__main__":
    # EXAMPLE test values
    domain = "test.ideafoundation.in"
    agent_id = "107649577889983698871"

    print("Generating NGINX config...")
    conf_path = write_agent_nginx_conf(domain, agent_id)

    # print("\n🧪 Testing and reloading NGINX...")
    # test_and_reload_nginx()
