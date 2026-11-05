# CONSOLE-001 C3 disposable SSH/tmux experiment

Research only. Read [the validation report](../../docs/console001/c3-interactive-tmux-validation.md)
first. The approved model allows native tmux controls and the fixed Linux account's
ordinary shell. This experiment does not attempt per-SUT confinement.

On an authorized disposable Linux amd64 Docker host:

```sh
sh research/console001-c3/run.sh
```

Requires Docker/BuildKit and a readable system CA bundle. Set
`CONSOLE001_CA_BUNDLE` to the existing trusted bundle if necessary; do not disable
TLS verification. Package installation uses the inherited Docker proxy settings.
The base image is digest-pinned; Debian package repositories can change, so record
the versions printed by each run rather than assuming identical future packages.

The runner checks the **local** Unix Docker socket, builds a **local research**
image, and runs one disposable container with `--network none`, no published ports,
no host bind mounts/volumes, resource limits and no-new-privileges. The fixture
requires root **inside that container** to create synthetic users and run sshd;
SSH uses non-root UID1000. It does not require privileged Docker or the host network.
The runner never publishes an image or changes application deployment.

`validate.py` refuses ordinary host execution, external network interfaces, or a
missing dedicated `/run/mock` tmpfs. Keys/passwords are generated only for this run;
private keys live in tmpfs and are never printed/exported. `--rm` removes the
container and tmpfs. Do not mount production directories or copy real credentials
into this image. The local image contains test code/packages, not generated keys.

`mock_uart.py` is a synthetic raw-byte echo with a byte counter; there is no UART,
minicom, BMC or production SQLite. `relay.py` is a loopback-only TCP fault injector,
not Gateway forwarding functionality. Fixtures create three sessions; automatic
connection startup only attaches. User-native commands are tested separately.

Exit0 means all **expected research observations** passed. One negative control
intentionally demonstrates that plain tmux attach closes SSH on Detach. It does
not mean a production Gateway, browser security, account sandbox or pilot passed.
Only status metadata is emitted; raw terminal buffers stay in test process memory.

Optional inspection of the local package versions (no fixture/credentials started):

```sh
docker --host=unix:///var/run/docker.sock run --rm --network none \
  --entrypoint dpkg-query console001-c3-research \
  -W '-f=${Package}=${Version}\n' tmux openssh-server openssh-client python3
```

After review, remove only this local image if no longer needed:

```sh
docker --host=unix:///var/run/docker.sock image rm console001-c3-research
```
