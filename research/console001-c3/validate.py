"""Disposable SSH/tmux feasibility experiment; no production Gateway or browser API.

Run via run.sh, never on a normal Linux host. Only JSON status/metadata is emitted.
"""
import fcntl
import json
import os
from pathlib import Path
import pty
import pwd
import re
import select
import shlex
import signal
import struct
import subprocess as sp
import termios
import time

SOCKET = '/home/console/socket/tmux'
ROOT = Path('/run/mock')
RESULTS = []
STARTUPS = []


def run(args, **kwargs):
    return sp.run(args, capture_output=True, text=True, timeout=10, **kwargs)


def checked(args, **kwargs):
    result = run(args, **kwargs)
    assert result.returncode == 0, (args[0], result.returncode, result.stderr)
    return result.stdout.strip()


def tmux(*args, user='console', socket=SOCKET):
    return run(['runuser', '-u', user, '--', 'tmux', '-N', '-S', socket, *args])


def until(predicate, seconds=4):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def record(name, ok, evidence):
    result = {'test': name, 'pass': bool(ok), 'evidence': evidence}
    RESULTS.append(result)
    print(json.dumps(result), flush=True)
    assert ok, name


def ssh(port=2222, key='key', known='known_hosts', user='console', safe=True):
    # Test fixture endpoints only. No browser or arbitrary remote execution API.
    argv = ['ssh', '-F', '/dev/null', '-i', str(ROOT / key), '-p', str(port),
            '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'GlobalKnownHostsFile=/dev/null',
            '-o', 'UserKnownHostsFile=' + str(ROOT / known), '-o', 'ConnectTimeout=3',
            '-o', 'ForwardAgent=no', '-o', 'ForwardX11=no',
            '-o', 'PermitLocalCommand=no', '-o', 'EscapeChar=none']
    if safe:
        argv += ['-o', 'ClearAllForwardings=yes']
    return argv + [user + '@127.0.0.1']


def startup(target, socket=SOCKET):
    # Proposed A2 grammar, not an approved inventory restriction. Exact match via '='.
    if not re.fullmatch(r'[A-Za-z0-9_]{1,64}', target):
        raise ValueError('invalid mock target')
    attach = shlex.join(['tmux', '-N', '-S', socket, 'attach-session', '-t', '=' + target])
    # exec tmux ALONE would close SSH on detach. Keep an ordinary interactive shell.
    command = 'if ' + attach + '; then exec /bin/bash -i; else exit 44; fi'
    STARTUPS.append(command)
    return command


class Terminal:
    def __init__(self, target='target', port=2222, user='console', socket=SOCKET, baseline=False):
        self.fd, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
        command = (shlex.join(['tmux', '-N', '-S', socket, 'attach-session', '-t', '=' + target])
                   if baseline else startup(target, socket))
        self.process = sp.Popen(ssh(port=port, user=user) + ['-tt', command],
                                stdin=slave, stdout=slave, stderr=slave,
                                env={**os.environ, 'TERM': 'xterm-256color'})
        os.close(slave)
        self.read(0.5)

    def read(self, seconds=0.3):
        output = b''
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if select.select([self.fd], [], [], 0.03)[0]:
                try:
                    output += os.read(self.fd, 65536)
                except OSError:
                    break
        return output

    def send(self, data):
        os.write(self.fd, data)

    def command(self, command):
        self.send(b'\x02:')
        self.read(0.15)
        self.send(command.encode() + b'\r')
        return self.read()

    def resize(self, cols, rows):
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
        self.process.send_signal(signal.SIGWINCH)

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()  # Only local mock Gateway SSH process, not tmux/pane.
            self.process.wait(timeout=5)
        os.close(self.fd)


def clients():
    return tmux('list-clients', '-F', '#{client_pid}:#{session_name}:#{client_width}x#{client_height}').stdout.splitlines()


def pane_pids():
    return tmux('list-panes', '-a', '-F', '#{session_name}:#{pane_pid}').stdout.splitlines()


def count():
    return int(Path('/home/console/target.count').read_text())


def main():
    assert os.geteuid() == 0 and Path('/.dockerenv').exists()
    assert set(os.listdir('/sys/class/net')) == {'lo'}, 'requires --network none'
    assert ROOT.is_dir() and os.path.ismount(ROOT), 'requires dedicated tmpfs'
    for name in ('console', 'outsider'):
        checked(['useradd', '-m', '-s', '/bin/bash', name])
        checked(['chpasswd'], input=name + ':' + os.urandom(32).hex() + '\n')
    Path('/run/sshd').mkdir(exist_ok=True)
    for key in ('host', 'key', 'wrong'):
        checked(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(ROOT / key)])
    for user in ('console', 'outsider'):
        home = Path('/home') / user
        (home / '.ssh').mkdir(mode=0o700)
        (home / '.ssh/authorized_keys').write_text((ROOT / 'key.pub').read_text())
        checked(['chown', '-R', user + ':' + user, str(home / '.ssh')])
    public = ' '.join((ROOT / 'host.pub').read_text().split()[:2])
    (ROOT / 'known_hosts').write_text('\n'.join('[127.0.0.1]:' + str(port) + ' ' + public
                                               for port in (2222, 2223)) + '\n')
    wrong = ' '.join((ROOT / 'wrong.pub').read_text().split()[:2])
    (ROOT / 'bad_hosts').write_text('[127.0.0.1]:2222 ' + wrong + '\n')
    (ROOT / 'sshd_config').write_text('''Port 2222
ListenAddress 127.0.0.1
HostKey /run/mock/host
PidFile /run/mock/sshd.pid
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM no
PermitRootLogin no
AllowUsers console outsider
DisableForwarding yes
PermitTunnel no
X11Forwarding no
PermitUserEnvironment no
''')
    checked(['/usr/sbin/sshd', '-t', '-f', str(ROOT / 'sshd_config')])
    checked(['/usr/sbin/sshd', '-f', str(ROOT / 'sshd_config'), '-E', str(ROOT / 'sshd.log')])
    checked(['install', '-d', '-m', '700', '-o', 'console', '-g', 'console', '/home/console/socket'])
    # FIXTURE setup only creates sessions. No deployment or real serial devices.
    for i, name in enumerate(('target', 'target_extra', 'other')):
        argv = ['runuser', '-u', 'console', '--', 'tmux', '-S', SOCKET]
        if i == 0:
            argv += ['-f', '/dev/null']
        checked(argv + ['new-session', '-d', '-s', name,
                        'python3 /research/mock_uart.py /home/console/' + name + '.count'])
    initial = pane_pids()
    print(json.dumps({'versions': {'tmux': checked(['tmux', '-V']),
                                  'openssh': run(['ssh', '-V']).stderr.strip(),
                                  'debian': Path('/etc/debian_version').read_text().strip(),
                                  'python': checked(['python3', '--version'])},
                      'socket': checked(['stat', '-c', '%U:%G %a', SOCKET]),
                      'uid': pwd.getpwnam('console').pw_uid}), flush=True)
    result = run(ssh(key='wrong') + ['true'])
    record('incorrect-key-denied', result.returncode == 255 and 'Permission denied' in result.stderr,
           'synthetic untrusted Ed25519 key rejected')
    result = run(ssh(known='bad_hosts') + ['true'])
    record('incorrect-host-key-denied', result.returncode == 255 and 'Host key verification failed' in result.stderr,
           'mismatched pinned host key rejected; StrictHostKeyChecking=yes')
    for target in ('missing', 'target_e'):
        t = Terminal(target)
        record('missing-exact-session:' + target, until(lambda: t.process.poll() is not None)
               and t.process.returncode == 44 and pane_pids() == initial,
               'exit44, no prefix match/fallback/create/delete, original pane PIDs unchanged')
        t.close()
    t = Terminal(socket='/home/console/socket/absent')
    record('missing-server-not-created', until(lambda: t.process.poll() is not None)
           and t.process.returncode == 44 and not Path('/home/console/socket/absent').exists(),
           'tmux -N failed; no missing socket/server created')
    t.close()
    t = Terminal(user='outsider')
    record('other-unix-account-denied', until(lambda: t.process.poll() is not None)
           and t.process.returncode == 44, 'directory0700/socket0600 deny unrelated UID; no chmod/ACL repair')
    t.close()
    # Negative control: common exec/attach-only approach does NOT satisfy detach-to-shell.
    t = Terminal(baseline=True)
    t.send(b'\x02d')
    record('attach-only-negative-control', until(lambda: t.process.poll() is not None),
           'plain attach terminates SSH after Detach; wrapper is necessary')
    t.close()
    a, b = Terminal(), Terminal()
    record('interactive-ssh-exact-attach', len(clients()) == 2
           and all(':target:' in x for x in clients()), 'two live SSH PTYs attached to exact target, not target_extra')
    a.resize(132, 44)
    record('ssh-pty-resize', until(lambda: any(x.endswith(':132x44') for x in clients())),
           'SIGWINCH/TIOCSWINSZ reached remote tmux client:132x44; no window-size option change')
    a.send(b'WRITER_A')
    b.send(b'WRITER_B')
    outputs = [a.read(), b.read()]
    decoded = [b''.join(bytes.fromhex(x.decode()) for x in re.findall(rb'UART:([0-9a-f]+)', output))
               for output in outputs]
    record('shared-concurrent-read-write', all(b'WRITER_A' in x and b'WRITER_B' in x for x in decoded),
           'both SSH clients received both synthetic writers; no writer lock')
    a.command('switch-client -t other')
    record('native-session-switch-allowed', any(':other:' in x for x in clients()),
           'user Ctrl+B : switch-client succeeded as explicitly approved; no per-SUT confinement')
    a.command('switch-client -t target')
    a.command('new-window -n user_window')
    record('native-window-create-allowed', 'user_window' in tmux('list-windows', '-t', '=target', '-F', '#{window_name}').stdout,
           'user-initiated native tmux new-window allowed; NOT Gateway startup')
    a.command('kill-window -t target:user_window')
    record('native-window-close-allowed', pane_pids() == initial,
           'user removed own test window; original mock processes unchanged')
    a.send(b'\x02d')
    a.read()
    a.send(b"printf '\\nSHELL_%s TERM=%s USER=%s\\n' 'ALIVE' \"$TERM\" \"$(id -un)\"\r")
    output = a.read()
    record('detach-to-ordinary-shell', b'SHELL_ALIVE TERM=xterm-256color USER=console' in output
           and a.process.poll() is None and len(clients()) == 1,
           'Detach leaves same SSH alive in bash -i as non-root console, TERM=xterm-256color')
    a.resize(117, 37)
    a.send(b"printf '\\nSIZE_%s\\n' \"$(stty size)\"\r")
    record('detached-shell-pty-resize', b'SIZE_37 117' in a.read(),
           'ordinary shell stty reports37 rows117 columns after resize')
    a.send(b"touch /home/console/user_command_marker; printf '\\nCOMMAND_%s\\n' 'DONE'\r")
    record('linux-account-commands-allowed', b'COMMAND_DONE' in a.read()
           and Path('/home/console/user_command_marker').exists(),
           'authorized user shell command ran with fixed account privilege, no sudo/root')
    a.close()
    record('disconnect-preserves-peer', b.process.poll() is None and len(clients()) == 1 and pane_pids() == initial,
           'intent=deliberate_disconnect; only local first SSH closed; peer and pane PIDs unchanged')
    before = count()
    b.close()
    record('all-disconnect-preserves-mocks', until(lambda: len(clients()) == 0) and pane_pids() == initial,
           'zero attachments, original three tmux sessions and mock UART processes preserved')
    c = Terminal()
    record('fresh-reconnect-no-replay', count() == before and len(clients()) == 1,
           'fresh SSH client reattached exact target; input byte counter did not increase')
    c.send(b'RECONNECT')
    record('fresh-input-only-on-reconnect', until(lambda: count() == before + len(b'RECONNECT')),
           'new explicit input counted once; no prior input queue replay')
    c.close()
    relay = sp.Popen(['python3', '/research/relay.py'], stdout=sp.PIPE, text=True)
    assert relay.stdout.readline().strip() == 'READY'
    d = Terminal(port=2223)
    record('relay-connection-attached', len(clients()) == 1, 'SSH through loopback-only disposable fault injector attached')
    before = count()
    relay.terminate()
    relay.wait(timeout=5)
    record('abrupt-transport-loss', until(lambda: d.process.poll() is not None)
           and d.process.returncode == 255 and pane_pids() == initial,
           'intent absent; injected TCP loss yielded SSH255; persistent sessions survived')
    d.close()
    e = Terminal()
    record('reconnect-after-loss', len(clients()) == 1 and count() == before,
           'new pinned-key SSH attachment succeeds, no synthetic input replay')
    e.close()
    result = run(ssh(safe=False) + ['-W', '127.0.0.1:2222'])
    record('gateway-forward-channel-denied', 'administratively prohibited' in result.stderr,
           'server rejects direct-tcpip even with client forwarding safeguards removed')
    result = run(ssh(safe=False) + ['-o', 'ExitOnForwardFailure=yes', '-R', '127.0.0.1:32222:127.0.0.1:2222', '-N'])
    record('gateway-remote-forward-denied', result.returncode == 255 and 'forwarding failed' in result.stderr,
           'server rejects remote forwarding; Gateway SSH uses ClearAllForwardings=yes')
    result = run(ssh() + ['-s', 'sftp'])
    record('sftp-subsystem-not-enabled', result.returncode != 0, 'no SFTP subsystem configured; interactive shell still intentionally available')
    rejected = 0
    for target in ('target;id', 'target\nid', '-target', 'target$(id)', '../target'):
        try:
            startup(target)
        except ValueError:
            rejected += 1
    record('startup-target-injection-rejected', rejected == 5, 'five malformed target names rejected before SSH; fixed quoted startup template')
    record('automatic-commands-attach-only', all('attach-session' in cmd and '-N' in cmd
           and not any(word in cmd for word in ('new-session', 'new-window', 'kill-', 'minicom', 'switch-client'))
           for cmd in STARTUPS), 'every automatic startup uses existing-session attach then shell only; user inputs separate')
    record('final-original-process-preservation', pane_pids() == initial
           and all(Path('/proc/' + row.split(':')[1]).exists() for row in initial),
           'original three pane processes alive with identical PIDs after lifecycle tests')
    record('ephemeral-key-permissions', (ROOT / 'key').stat().st_mode & 0o777 == 0o600
           and os.path.ismount(ROOT), 'keys generated only inside disposable tmpfs; never emitted, exported or committed')
    print(json.dumps({'summary': 'PASS', 'checks': len(RESULTS),
                      'classification': 'FEASIBLE WITH PREREQUISITES',
                      'scope': 'SSH/tmux mock transport only; no browser/Gateway/security acceptance'}), flush=True)


if __name__ == '__main__':
    main()
