"""Actual image-only Phase E Compose, synthetic custody, egress and cold recovery.

Uses only its own temporary bind paths/project; never /data or real devices.
Run after building sut-console001-e:local and the existing console mock fixture.
"""

import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.environ.get("SUT_CONSOLE_DEPLOY_IMAGE", "sut-console001-e:local")
PREVIOUS = os.environ.get("SUT_CONSOLE_PREVIOUS_IMAGE", "sut-console001-e:previous")


def docker(*args, data=None, ok=True):
    result = subprocess.run(
        ["docker", "--host=unix:///var/run/docker.sock", *args], input=data, text=True, capture_output=True
    )
    if ok and result.returncode:
        # No raw subprocess output: auth or config may appear there.
        raise AssertionError(f"Disposable deployment command failed: {args[0]} (exit {result.returncode})")
    return result.stdout if ok else result


def main():
    project = "console-e-" + secrets.token_hex(4)
    subnet = f"172.29.{secrets.randbelow(200) + 20}"
    with tempfile.TemporaryDirectory(prefix="console-e-") as directory:
        base = Path(directory)
        root, data = base / "custody", base / "data"
        root.mkdir(mode=0o700)
        data.mkdir()
        policy = base / "policy.json"
        policy.write_text(
            json.dumps(
                {
                    "version": 1,
                    "host_ipv4": [subnet + ".1"],
                    "deny_cidrs": [subnet + ".4/32"],
                    "ssh_ports": [22],
                }
            )
        )
        policy.chmod(0o644)  # Nonsecret file-only mount, parent remains private.
        env = base / "console.env"
        env.write_text(
            "\n".join(
                (
                    f"SECRET_KEY={secrets.token_urlsafe(48)}",
                    f"CONSOLE_IMAGE={IMAGE}",
                    f"CONSOLE_ROOT={root}",
                    f"CONSOLE_POLICY_FILE={policy}",
                    "CONSOLE_ENABLED=true",
                    "CONSOLE_ALLOW_INSECURE_HTTP=true",
                    "CONSOLE_HTTP_RISK_ACK=I_ACCEPT_PLAINTEXT_CONSOLE",
                    'CONSOLE_ALLOWED_ORIGINS=["http://127.0.0.1:5088"]',
                    "COOKIE_SECURE=false",
                )
            )
            + "\n"
        )
        env.chmod(0o600)
        # Copy only Compose artifacts; the operator path has no source/build context.
        for name in ("compose.deploy.yaml", "compose.console.yaml"):
            (base / name).write_bytes((ROOT / name).read_bytes())
        overrides = {
            "services": {
                "sut-management": {
                    "healthcheck": {"interval": "2s", "timeout": "2s", "start_period": "1s", "retries": 30},
                    "volumes": [
                        {
                            "type": "bind",
                            "source": str(data),
                            "target": "/app/data",
                            "bind": {"create_host_path": False},
                        }
                    ],
                },
                "mock-ssh": {
                    "image": "sut-console001-c-mock:local",
                    "networks": {"console-egress": {"ipv4_address": subnet + ".3"}},
                },
                "sensitive-ssh": {
                    "image": "sut-console001-c-mock:local",
                    "networks": {"console-egress": {"ipv4_address": subnet + ".4"}},
                },
            },
            "networks": {
                "console-egress": {"internal": True, "ipam": {"config": [{"subnet": subnet + ".0/24"}]}}
            },
        }
        override = base / "test-only.json"
        override.write_text(json.dumps(overrides))
        args = [
            "compose",
            "--env-file",
            str(env),
            "-p",
            project,
            "-f",
            str(base / "compose.deploy.yaml"),
            "-f",
            str(base / "compose.console.yaml"),
            "-f",
            str(override),
        ]

        def compose(*values, **kw):
            return docker(*args, *values, **kw)

        def identity(service):
            return compose("ps", "-q", service).strip()

        def wait_health(service):
            for _ in range(100):
                container = identity(service)
                if (
                    container
                    and docker("inspect", "--format", "{{.State.Health.Status}}", container).strip()
                    == "healthy"
                ):
                    return container
                time.sleep(0.3)
            raise AssertionError(f"Synthetic {service} health timeout")

        try:
            docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "0:0",
                "--mount",
                f"type=bind,src={root},dst=/custody",
                "--entrypoint",
                "python",
                IMAGE,
                "-m",
                "app.console_deployment",
                "provision",
                "--path",
                "/custody",
            )
            docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "0:0",
                "--mount",
                f"type=bind,src={data},dst=/data",
                "--entrypoint",
                "python",
                IMAGE,
                "-c",
                "import os; os.chown('/data',10001,10001); os.chmod('/data',0o700)",
            )
            # Console-on fresh install in its own empty bind; keep it separate from
            # the existing-data upgrade fixture (never wipe/replace a database).
            fresh = base / "fresh-data"
            docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "0:0",
                "--mount",
                f"type=bind,src={base},dst=/fixture",
                "--entrypoint",
                "python",
                IMAGE,
                "-c",
                "import os; os.mkdir('/fixture/fresh-data',0o700); os.chown('/fixture/fresh-data',10001,10001)",
            )
            overrides["services"]["sut-management"]["volumes"][0]["source"] = str(fresh)
            override.write_text(json.dumps(overrides))
            compose("config", "--quiet")
            compose("up", "-d", "--no-build", "--pull", "never")
            fresh_web = wait_health("sut-management")
            docker(
                "exec",
                fresh_web,
                "python",
                "-c",
                "import sqlite3; c=sqlite3.connect('/app/data/sut.db'); assert c.execute('select version_num from alembic_version').fetchone()[0]=='console001_b01'; assert c.execute('select count(*) from users').fetchone()[0]==0",
            )
            compose("stop", "sut-management", "console-broker")
            overrides["services"]["sut-management"]["volumes"][0]["source"] = str(data)
            override.write_text(json.dumps(overrides))
            print(
                "PASS: Console-on fresh empty-bind installation migrates before healthy; no default accounts or data replacement",
                flush=True,
            )
            # Upgrade from an actual pre-Phase-E main image, not a relabelled candidate.
            seed = """from app.core.database import make_engine,unit_of_work,utcnow
from app.models.domain import Lab,User,SUT,CurrentUsage,QueueEntry,Reservation,UsageHistory
from app.services.accounts import HASHER
from datetime import timedelta
import secrets
now=utcnow()
with unit_of_work(make_engine('sqlite:////app/data/sut.db'),write=True) as d:
 for identity in (1,2):
  d.add(User(id=identity,username='synthetic'+str(identity),display_name='Synthetic',team='Mock',email='synthetic'+str(identity)+'@example.test',password_hash=HASHER.hash(secrets.token_urlsafe(24)),role='super_admin' if identity==1 else 'user',must_change_password=False))
 d.add(Lab(id=1,name='Recovery canary',location='Synthetic')); d.flush()
 for identity in (1,2,3): d.add(SUT(id=identity,lab_id=1,name='Mock '+str(identity),normalized_name='mock '+str(identity),platform='Mock',owner_team='Mock'))
 d.flush()
 d.add(CurrentUsage(sut_id=1,user_id=1,start_time=now,expected_end_time=now+timedelta(hours=8)))
 d.add(QueueEntry(sut_id=1,user_id=2,requested_duration_minutes=60))
 d.add(Reservation(sut_id=2,user_id=1,start_time=now+timedelta(days=1),end_time=now+timedelta(days=1,hours=1),purpose='Synthetic'))
 d.add(UsageHistory(sut_id=3,user_id=1,usage_key='synthetic-completed',start_time=now-timedelta(hours=2),end_time=now-timedelta(hours=1),duration_minutes=60,release_reason='user'))
"""
            docker(
                "run",
                "--rm",
                "-i",
                "--network",
                "none",
                "--user",
                "10001:10001",
                "--mount",
                f"type=bind,src={data},dst=/app/data",
                "--entrypoint",
                "python",
                PREVIOUS,
                "-c",
                "from alembic import command; from alembic.config import Config; import sys; command.upgrade(Config('/app/alembic.ini'),'head'); exec(sys.stdin.read())",
                data=seed,
            )
            docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "0:0",
                "--mount",
                f"type=bind,src={base},dst=/fixture",
                "--entrypoint",
                "python",
                IMAGE,
                "-c",
                "import shutil,os; from pathlib import Path; p=Path('/fixture/pre-upgrade-db'); shutil.copytree('/fixture/data',p); os.chown(p,10001,10001); [os.chown(f,10001,10001) for f in p.rglob('*')]",
            )
            fingerprint = "import sqlite3,json,hashlib; c=sqlite3.connect('file:/app/data/sut.db?mode=ro',uri=True); print(hashlib.sha256(json.dumps({t:c.execute('select * from '+t+' order by id').fetchall() for t in ['users','labs','suts','current_usages','queue_entries','reservations','usage_histories']},sort_keys=True).encode()).hexdigest())"
            before = docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "10001:10001",
                "--mount",
                f"type=bind,src={data},dst=/app/data",
                "--entrypoint",
                "python",
                PREVIOUS,
                "-c",
                fingerprint,
            )
            compose("config", "--quiet")
            started = compose("up", "-d", "--no-build", "--pull", "never", ok=False)
            if started.returncode:
                # Only namespace initializer emits no credential-bearing values.
                print(compose("logs", "--no-log-prefix", "console-network", ok=False).stdout)
                print(started.stderr[-1500:])
                raise AssertionError("Image-only Compose startup failed")
            web = wait_health("sut-management")
            broker = wait_health("console-broker")
            guard = wait_health("console-network")
            for container, uid in ((web, 10001), (broker, 10002), (guard, 10003)):
                probe = (
                    "from pathlib import Path; s=Path('/proc/1/status').read_text(); assert 'Uid:\\t%d\\t%d' in s; assert 'CapEff:\\t0000000000000000' in s; assert 'NoNewPrivs:\\t1' in s"
                    % (uid, uid)
                )
                docker("exec", container, "python", "-c", probe)
            webmounts = json.loads(docker("inspect", web))[0]["Mounts"]
            brokermounts = json.loads(docker("inspect", broker))[0]["Mounts"]
            assert not any(m["Destination"] == "/run/console-keys" for m in webmounts)
            assert not any(m["Destination"] == "/app/data" for m in brokermounts)
            assert compose("port", "sut-management", "80").strip() == "127.0.0.1:5088"
            docker("exec", web, "python", "-m", "app.console_deployment", "preflight")
            print(
                "PASS: actual image-only Compose, 5088:80, UID10001/10002/10003 zero caps, separate DB/KEK and authenticated preflight",
                flush=True,
            )
            mock = identity("mock-ssh")
            docker("exec", "-d", mock, "python", "-m", "http.server", "80", "--bind", "0.0.0.0")
            time.sleep(0.3)
            docker(
                "exec",
                mock,
                "python",
                "-c",
                "import socket; socket.create_connection(('127.0.0.1',80),2).close(); socket.create_connection(('"
                + subnet
                + ".4',22),2).close()",
            )
            code = """import socket,sys
host=sys.argv[1]
s=socket.create_connection((host,22),2); assert s.recv(64).startswith(b'SSH-'); s.close()
for target,port in [(host,80),(sys.argv[2],22),(sys.argv[3],22),('127.0.0.1',22),('169.254.169.254',80)]:
 try: socket.create_connection((target,port),.3)
 except OSError: continue
 raise AssertionError('Egress boundary bypassed')
print('PASS: raw sockets permit mock SSH only and reject sensitive SSH, gateway, localhost, metadata and non-SSH port')
"""
            docker("exec", broker, "python", "-c", code, subnet + ".3", subnet + ".4", subnet + ".1")
            print("PASS: namespace firewall raw-socket egress restrictions (not classifier-only)", flush=True)
            # Real broker probe uses this same policy/firewall, before any SSH userauth.
            probe = """import asyncio,sys
from app.console_broker.ipc import BrokerClient,private_key_file
async def go():
 c=BrokerClient('/run/console/broker.sock',private_key_file('/run/console-auth'))
 r=await c.call('probe_key',host=sys.argv[1],port=22,transport='bmc'); assert r['fingerprint'].startswith('SHA256:')
asyncio.run(go())
"""
            docker("exec", web, "python", "-c", probe, subnet + ".3")
            fixture = json.loads(docker("exec", mock, "cat", "/run/mock.json"))
            fixture["host"] = subnet + ".3"
            enroll = """import asyncio,base64,json,sys
from app.console_broker.ipc import BrokerClient,private_key_file
from app.core.database import make_engine,unit_of_work
from app.models.console import ConsoleClient,ConsoleCredential
v=json.load(sys.stdin)
async def go():
 c=BrokerClient('/run/console/broker.sock',private_key_file('/run/console-auth'))
 import asyncssh
 pin=await c.call('probe_key',host=v['host'],port=22,transport='uart')
 assert pin['fingerprint']==asyncssh.import_public_key(v['public_key']).get_fingerprint('sha256')
 r=await c.call('validate_client',target={'host':v['host'],'port':22,'transport':'uart','public_key':pin['public_key']},user_id=1,credential={'method':'password','username':v['username'],'secret':v['password']},client_security_id='client',credential_security_id='credential',generation=1)
 e=r['envelope']
 for k in ('ciphertext','nonce','wrapped_data_key','wrap_nonce'): e[k]=base64.b64decode(e[k])
 with unit_of_work(make_engine('sqlite:////app/data/sut.db'),write=True) as d:
  client=ConsoleClient(security_id='client',lab_id=1,name='Synthetic Client',normalized_name='synthetic client',ipv4=v['host'],ssh_username=v['username'],auth_method='password',updated_by=1)
  d.add(client); d.flush()
  d.add(ConsoleCredential(security_id='credential',client_security_id='client',method='password',generation=1,created_by=1,**e))
asyncio.run(go())
"""
            docker("exec", "-i", web, "python", "-c", enroll, data=json.dumps(fixture))
            fixture.clear()
            docker("exec", web, "python", "-m", "app.console_deployment", "preflight")
            compose("stop", "sut-management", "console-broker")
            # Cold backup DB only; keyring independently retained in its disjoint custody directory.
            mount = ["--mount", f"type=bind,src={base},dst=/fixture"]
            snapshot = """import sqlite3,shutil,os
from pathlib import Path
shutil.copytree('/fixture/data','/fixture/cold-db')
shutil.copytree('/fixture/cold-db','/fixture/restored-db')
for p in Path('/fixture/restored-db').rglob('*'): os.chown(p,10001,10001)
os.chown('/fixture/restored-db',10001,10001)
"""
            docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "0:0",
                *mount,
                "--entrypoint",
                "python",
                IMAGE,
                "-c",
                snapshot,
            )
            # Recreate from the populated persistent bind; migration is idempotent.
            compose("up", "-d", "--no-build", "--pull", "never")
            web = wait_health("sut-management")
            integrity = """import sqlite3
c=sqlite3.connect('/app/data/sut.db'); assert c.execute('pragma integrity_check').fetchone()[0]=='ok'; assert not c.execute('pragma foreign_key_check').fetchall(); assert c.execute('select version_num from alembic_version').fetchone()[0]=='console001_b01'; assert c.execute('select count(*) from users').fetchone()[0]==2; assert c.execute('select count(*) from labs').fetchone()[0]==1; assert all(c.execute('select count(*) from '+t).fetchone()[0]==n for t,n in [('suts',3),('current_usages',1),('queue_entries',1),('reservations',1),('usage_histories',1)])
"""
            docker("exec", web, "python", "-c", integrity)
            assert docker("exec", web, "python", "-c", fingerprint) == before
            compose("stop", "sut-management", "console-broker")
            overrides["services"]["sut-management"]["volumes"][0]["source"] = str(base / "restored-db")
            override.write_text(json.dumps(overrides))
            compose("up", "-d", "--no-build", "--pull", "never")
            web = wait_health("sut-management")
            docker("exec", web, "python", "-c", integrity)
            assert docker("exec", web, "python", "-c", fingerprint) == before
            print(
                "PASS: populated bind upgrade/recreate and empty-directory cold restore, matching image/custody, account/Lab/schema/integrity/FKs preserved",
                flush=True,
            )
            # Old main image reads only its own compatible pre-upgrade backup; no schema downgrade.
            docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "10001:10001",
                "--mount",
                f"type=bind,src={base / 'pre-upgrade-db'},dst=/app/data",
                "--entrypoint",
                "python",
                PREVIOUS,
                "-c",
                integrity,
            )
            assert (
                docker(
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--user",
                    "10001:10001",
                    "--mount",
                    f"type=bind,src={base / 'pre-upgrade-db'},dst=/app/data",
                    "--entrypoint",
                    "python",
                    PREVIOUS,
                    "-c",
                    fingerprint,
                )
                == before
            )
            print(
                "PASS: old-image rollback against matching pre-upgrade backup; accounts, usage, queue, reservation and history retained",
                flush=True,
            )
            # Explicit HTTP attestation omission fails without touching migration/data.
            result = docker(
                "exec",
                "-e",
                "CONSOLE_HTTP_RISK_ACK=",
                web,
                "python",
                "-m",
                "app.console_deployment",
                "preflight",
                ok=False,
            )
            assert result.returncode != 0
            compose("stop", "console-broker")
            edit_key = "import shutil,json,secrets,base64; from pathlib import Path; p=Path('/fixture/custody/keys/keyring'); b=Path('/fixture/offline-key-backup'); b.mkdir(mode=0o700); shutil.copy2(p,b/'keyring'); v=json.loads(p.read_text()); v['keys']={k:base64.b64encode(secrets.token_bytes(32)).decode() for k in v['keys']}; p.write_text(json.dumps(v))"
            docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "0:0",
                *mount,
                "--entrypoint",
                "python",
                IMAGE,
                "-c",
                edit_key,
            )
            compose("up", "-d", "--no-build", "--pull", "never", "console-broker")
            wait_health("console-broker")
            rejected = docker("exec", web, "python", "-m", "app.console_deployment", "preflight", ok=False)
            assert rejected.returncode != 0
            compose("stop", "console-broker")
            docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "0:0",
                *mount,
                "--entrypoint",
                "python",
                IMAGE,
                "-c",
                "import shutil; shutil.copy2('/fixture/offline-key-backup/keyring','/fixture/custody/keys/keyring')",
            )
            compose("up", "-d", "--no-build", "--pull", "never", "console-broker")
            wait_health("console-broker")
            docker("exec", web, "python", "-m", "app.console_deployment", "preflight")
            print(
                "PASS: syntactically valid wrong KEK rejects retained credential at authenticated startup preflight; independent exact key backup recovers",
                flush=True,
            )
            compose("stop", "console-broker")
            result = docker("exec", web, "python", "-m", "app.console_deployment", "preflight", ok=False)
            assert result.returncode != 0
            print(
                "PASS: absent HTTP acknowledgement or unavailable Broker fails deployment preflight closed",
                flush=True,
            )
        finally:
            compose("down", "--remove-orphans", ok=False)
            # UID-owned disposable bind contents are removed only via this fixture's private mount.
            docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "0:0",
                "--mount",
                f"type=bind,src={base},dst=/fixture",
                "--entrypoint",
                "python",
                IMAGE,
                "-c",
                "import shutil; from pathlib import Path; [shutil.rmtree(p) for p in Path('/fixture').iterdir() if p.is_dir()]",
                ok=False,
            )


if __name__ == "__main__":
    main()
