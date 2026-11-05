"""Real Chromium -> isolated Gateway/Broker/OpenSSH/tmux; no real-device access.

Run through SUT_CONSOLE_BROWSER=1 python scripts/console_mock_smoke.py.
Only the synthetic HTTP UI is published on a random host-loopback port.
Passwords, SSH credentials and terminal payloads are never printed or recorded.
"""

import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time

from playwright.sync_api import sync_playwright, expect


def run_browser_checks(docker, name, fixture, web_mounts, containers):
    web = name + "-web-ui"
    containers.append(web)
    docker(
        "run",
        "-d",
        "--name",
        web,
        "--network",
        "bridge",
        "--user",
        "10001:10001",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--publish",
        "127.0.0.1::8080",
        *web_mounts,
        "-e",
        "PYTHONPATH=/app",
        "--entrypoint",
        "sleep",
        "sut-console001-c-mock:local",
        "infinity",
    )
    port = docker(
        "inspect", "--format", '{{(index (index .NetworkSettings.Ports "8080/tcp") 0).HostPort}}', web
    ).strip()
    base = "http://127.0.0.1:" + port
    data = {
        "web_password": secrets.token_urlsafe(30),
        "login_secret": secrets.token_urlsafe(48),
        "r1_login_delay": float(os.environ.get("SUT_CONSOLE_R1_LOGIN_DELAY", "0")),
    }
    # Server parses stdin once and clears it; no env/argv/file secrets.
    with tempfile.TemporaryFile(mode="w+") as output:
        process = subprocess.Popen(
            [
                "docker",
                "--host=unix:///var/run/docker.sock",
                "exec",
                "-i",
                web,
                "python",
                "/mock/browser_server.py",
            ],
            stdin=subprocess.PIPE,
            stdout=output,
            stderr=output,
            text=True,
        )
        process.stdin.write(json.dumps(data))
        process.stdin.close()
        try:
            with sync_playwright() as p:
                executable = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")
                browser = p.chromium.launch(**({"executable_path": executable} if executable else {}))
                context = browser.new_context(viewport={"width": 1440, "height": 1100})
                context.add_init_script(
                    path=str(Path(__file__).resolve().parents[1] / "tests/console_mock/browser_lifecycle.js")
                )
                page = context.new_page()
                for _ in range(120):
                    try:
                        if context.request.get(base + "/health", timeout=1000).ok:
                            break
                    except Exception:
                        pass
                    if process.poll() is not None:
                        raise AssertionError("synthetic Gateway exited")
                    time.sleep(0.1)
                else:
                    raise AssertionError("synthetic Gateway readiness timeout")
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                checks = []

                def passed(name):
                    checks.append(name)
                    print("PASS browser:", name, flush=True)

                def login(page, user="uiroot"):
                    page.goto(base + "/login")
                    page.get_by_label("Username", exact=True).fill(user)
                    page.get_by_label("Password", exact=True).fill(data["web_password"])
                    page.get_by_role("button", name="Sign in", exact=True).click()
                    page.wait_for_url(base + "/")

                def api(page, path, method="GET", value=None):
                    # Function returns status/projection, never logs its arguments.
                    return page.evaluate(
                        """async ({path,method,value})=>{
                     const csrf=(await (await fetch('/api/v1/auth/csrf')).json()).csrf_token;
                     const response=await fetch('/api/v1'+path,{method,headers:{'X-CSRF-Token':csrf,'Content-Type':'application/json'},...(value!==null?{body:JSON.stringify(value)}:{})});
                     return {status:response.status,data:await response.json()};
                    }""",
                        {"path": path, "method": method, "value": value},
                    )

                def confirm_trust(page):
                    expect(page.get_by_role("heading", name="Verify SSH Host Key")).to_be_visible(
                        timeout=15000
                    )
                    expect(page.locator("#dialog-text")).to_contain_text("Fingerprint: SHA256:")
                    expect(page.locator("#dialog-accept")).to_be_disabled()
                    page.locator("#dialog-ack").check()
                    page.locator("#dialog-accept").click()

                def open_console(context, sut):
                    tab = context.new_page()
                    tab.on("pageerror", lambda e: errors.append(str(e)))
                    tab.goto(base + f"/suts/{sut}/console")
                    expect(tab.locator("#endpoint-summary")).not_to_contain_text("Loading")
                    return tab

                login(page)
                inventory = api(page, "/suts")["data"]["items"]
                sut = next(item["id"] for item in inventory if item["name"] == "UI UART")
                maintenance = next(item["id"] for item in inventory if item["name"] == "UI Maintenance")
                page.goto(base + "/admin/console-clients")
                page.get_by_label("Client name", exact=True).fill("Synthetic SSH Client")
                page.get_by_label("Client IPv4", exact=True).fill(fixture["host"])
                page.get_by_label("Fixed SSH username", exact=True).fill(fixture["username"])
                page.get_by_label("New / replacement SSH password", exact=True).fill(fixture["password"])
                page.get_by_role("button", name="Save Client", exact=True).click()
                confirm_trust(page)
                expect(page.locator("#console-feedback")).to_contain_text("Client saved", timeout=15000)
                expect(page.locator("#client-password")).to_have_value("")
                expect(page.locator("#client-list")).to_contain_text("Configured")
                passed("Admin initial host-key acknowledgement and auth-before-create, secret field cleared")
                page.get_by_label("Notes (optional, no secrets)", exact=True).fill("Synthetic operator notes")
                page.get_by_role("button", name="Save Client", exact=True).click()
                expect(page.locator("#client-list")).to_contain_text("Synthetic operator notes")
                passed("Admin metadata editing without credential reveal")
                page.goto(base + f"/suts/{sut}/connections")
                page.get_by_label("Console Client (same Lab)", exact=True).select_option(
                    label="Synthetic SSH Client · " + fixture["host"] + ":22"
                )
                page.get_by_label("Existing tmux session", exact=True).fill("existing")
                page.get_by_role("button", name="Save UART", exact=True).click()
                expect(page.locator("#console-feedback")).to_contain_text("Connection saved")
                page.get_by_label("BMC RFC1918 private IPv4", exact=True).fill(fixture["host"])
                page.get_by_role("button", name="Save BMC", exact=True).click()
                expect(page.locator("#bmc-summary")).to_contain_text(fixture["host"])
                expect(page.locator("#mapping-history")).to_contain_text("uart")
                expect(page.locator("#mapping-history")).to_contain_text("bmc")
                passed("RD-compatible independent mapping save/history; no inventory privilege shortcut")
                terminal = open_console(context, sut)
                terminal.get_by_role("button", name="Connect", exact=True).click()
                expect(terminal.locator("#connection-state")).to_have_text("Connected", timeout=15000)
                expect(terminal.locator(".xterm-helper-textarea")).to_be_focused()
                terminal.locator(".xterm-helper-textarea").press_sequentially("BROWSER_UART_PROOF", delay=20)
                expect(terminal.locator("#terminal")).to_contain_text("BROWSER_UART_PROOF", timeout=10000)
                expect(terminal.locator("#transport-warning")).to_be_visible()
                passed("Real UART WebSocket/tmux read-write and explicit plaintext warning")
                terminal.get_by_role("button", name="Increase terminal font").click()
                expect(terminal.locator("#font-size")).to_have_text("15px")
                terminal.get_by_role("button", name="Decrease terminal font").click()
                expect(terminal.locator("#font-size")).to_have_text("14px")
                terminal.locator(".xterm-helper-textarea").press("Control+f")
                terminal.locator("#search-term").fill("browser_uart_proof")
                terminal.get_by_role("button", name="Next match", exact=True).click()
                expect(terminal.locator("#search-result")).to_have_text("Match highlighted")
                terminal.get_by_role("button", name="Previous match", exact=True).click()
                terminal.get_by_role("button", name="Close search", exact=True).click()
                passed("Font controls and case-insensitive local previous/next Ctrl+F search")
                terminal.get_by_role("button", name="Fullscreen", exact=True).click()
                expect(terminal.locator("#terminal-stage")).to_have_js_property("clientWidth", 1440)
                terminal.keyboard.press("Escape")
                terminal.wait_for_function("!document.fullscreenElement")
                passed("Fullscreen / Esc and fit observer")

                # Synthetic clipboard event follows the same native paste handler without OS credentials.
                def paste(tab, value):
                    tab.locator(".xterm-helper-textarea").evaluate(
                        """(node,value)=>{const data=new DataTransfer();data.setData('text/plain',value);node.dispatchEvent(new ClipboardEvent('paste',{bubbles:true,cancelable:true,clipboardData:data}));}""",
                        value,
                    )

                paste(terminal, "PASTE_SINGLE_PROOF")
                terminal.wait_for_timeout(300)
                expect(terminal.locator("#terminal")).to_contain_text("PASTE_SINGLE_PROOF")
                paste(terminal, "MULTILINE_ONE\r\nMULTILINE_TWO")
                expect(terminal.get_by_role("heading", name="Confirm multiline paste")).to_be_visible()
                expect(terminal.locator("#dialog-text")).to_contain_text("2 lines")
                terminal.locator("#dialog-accept").click()
                expect(terminal.locator("#terminal")).to_contain_text("MULTILINE_TWO")
                paste(terminal, "CANCELLED_PASTE\nSECOND")
                terminal.get_by_role("button", name="Cancel", exact=True).click()
                paste(terminal, "HIDDEN\x1bCONTROL")
                expect(terminal.locator("#console-feedback")).to_contain_text("hidden control")
                passed(
                    "Bounded single/multiline CRLF paste, confirmation cancel and hidden-control rejection"
                )
                paste(terminal, "BIDI_\u202eHIDDEN")
                expect(terminal.locator("#console-feedback")).to_contain_text("hidden control")
                paste(terminal, "C1_\u0085HIDDEN")
                expect(terminal.locator("#console-feedback")).to_contain_text("hidden control")
                terminal.evaluate(
                    """Object.defineProperty(navigator,'clipboard',{configurable:true,value:{readText:()=>Promise.reject(new Error('synthetic denial'))}})"""
                )
                terminal.locator("#terminal").click(button="right")
                expect(terminal.locator("#clipboard-help")).to_contain_text("Ctrl+V")
                passed("Right-click clipboard denial provides Ctrl+V fallback")
                context.grant_permissions(["clipboard-read", "clipboard-write"])
                page.bring_to_front()
                page.evaluate("navigator.clipboard.writeText('CTRLV_NATIVE_PROOF')")
                terminal.bring_to_front()
                terminal.locator(".xterm-helper-textarea").press("Control+v")
                expect(terminal.locator("#terminal")).to_contain_text("CTRLV_NATIVE_PROOF")
                passed("Native Ctrl+V paste works after right-click Clipboard API denial")
                attempts = []

                def transient_attach(route):
                    attempts.append(time.monotonic())
                    if len(attempts) < 3:
                        route.abort("failed")
                    else:
                        route.continue_()

                terminal.route("**/api/v1/console/sessions/*/attach", transient_attach)
                terminal.evaluate(
                    "window.__consoleTestSocket.dispatchEvent(new CloseEvent('close',{code:1006}))"
                )
                expect(terminal.locator("#connection-state")).to_have_text("Reconnecting")
                expect(terminal.locator("#connection-state")).to_have_text("Connected", timeout=20000)
                assert (
                    len(attempts) == 3
                    and attempts[1] - attempts[0] >= 1.7
                    and attempts[2] - attempts[1] >= 3.7
                )
                terminal.unroute("**/api/v1/console/sessions/*/attach", transient_attach)
                expect(terminal.locator("#quota-summary")).to_contain_text("1/10")
                passed(
                    "UI simulated browser-close and aborted attach requests use finite backoff and same-slot ticket generations"
                )
                terminal.get_by_role("button", name="Reconnect", exact=True).click()
                terminal.get_by_role("button", name="Cancel", exact=True).click()
                expect(terminal.locator("#connection-state")).to_have_text("Connected")
                terminal.get_by_role("button", name="Reconnect", exact=True).click()
                terminal.locator("#dialog-accept").click()
                expect(terminal.locator("#connection-state")).to_have_text("Connected", timeout=15000)
                expect(terminal.locator("#reconnect-boundary")).to_be_visible()
                expect(terminal.locator("#terminal")).to_contain_text("BROWSER_UART_PROOF")
                passed("Connected Reconnect confirmation/cancel, retained RAM buffer and divider")
                # End-of-test isolation scans occur after the rest of the scenarios below.
                terminal.get_by_role("button", name="Disconnect", exact=True).click()
                expect(terminal.locator("#connection-state")).to_have_text("Disconnected")
                terminal.locator("#console-mode").select_option("bmc")
                expect(terminal.locator("#connection-state")).to_have_text("Not Connected")
                terminal.get_by_role("button", name="Connect", exact=True).click()
                confirm_trust(terminal)
                expect(terminal.locator("#bmc-auth")).to_be_visible(timeout=15000)
                expect(terminal.locator("#bmc-attempts")).to_contain_text("3 authentication")
                for attempts in [2, 1]:
                    terminal.get_by_label("BMC username", exact=True).fill(fixture["username"])
                    terminal.get_by_label("BMC password", exact=True).fill(secrets.token_urlsafe(28))
                    terminal.get_by_role("button", name="Authenticate", exact=True).click()
                    expect(terminal.locator("#bmc-attempts")).to_contain_text(
                        str(attempts) + " authentication", timeout=15000
                    )
                    expect(terminal.get_by_label("BMC password", exact=True)).to_have_value("")
                terminal.get_by_label("BMC username", exact=True).fill(fixture["username"])
                terminal.get_by_label("BMC password", exact=True).fill(secrets.token_urlsafe(28))
                terminal.get_by_role("button", name="Authenticate", exact=True).click()
                expect(terminal.locator("#connection-state")).to_have_text("Failed", timeout=15000)
                expect(terminal.locator("#bmc-auth")).to_be_hidden()
                terminal.get_by_role("button", name="Retry", exact=True).click()
                expect(terminal.locator("#bmc-auth")).to_be_visible(timeout=15000)
                expect(terminal.locator("#bmc-attempts")).to_contain_text("3 authentication")
                expect(terminal.get_by_label("BMC password", exact=True)).to_have_value("")
                terminal.get_by_label("BMC username", exact=True).fill(fixture["username"])
                terminal.get_by_label("BMC password", exact=True).fill(fixture["password"])
                terminal.get_by_role("button", name="Authenticate", exact=True).click()
                expect(terminal.locator("#connection-state")).to_have_text("Connected", timeout=15000)
                terminal.get_by_role("button", name="Disconnect", exact=True).click()
                terminal.get_by_role("button", name="Reconnect", exact=True).click()
                expect(terminal.locator("#bmc-auth")).to_be_visible(timeout=15000)
                expect(terminal.get_by_label("BMC password", exact=True)).to_have_value("")
                expect(terminal.locator("#bmc-attempts")).to_contain_text("3 authentication")
                terminal.get_by_role("button", name="Disconnect", exact=True).click()
                passed(
                    "BMC host-key trust, exact remaining attempts, cleared password and fresh reconnect prompt"
                )
                # Return to UART; inspect terminal controls and native Detach in the real SSH PTY.
                terminal.locator("#console-mode").select_option("uart")
                terminal.get_by_role("button", name="Connect", exact=True).click()
                expect(terminal.locator("#connection-state")).to_have_text("Connected", timeout=15000)
                passed("Mode switch back to UART requires and completes explicit Connect")
                terminal.evaluate(
                    """() => {window.__keyCount=0; const original=WebSocket.prototype.send; WebSocket.prototype.send=function(value){if(typeof value==='string' && JSON.parse(value).type==='send_key')window.__keyCount++;return original.call(this,value)};}"""
                )
                for key in ["esc", "tab", "ctrl_c", "ctrl_d", "ctrl_z"]:
                    terminal.locator("#send-key").select_option(key)
                    terminal.get_by_role("button", name="Send Key", exact=True).click()
                assert terminal.evaluate("window.__keyCount") == 5
                passed("All five Send Key controls send once while writable")
                for _ in range(15):
                    terminal.get_by_role("button", name="Increase terminal font").click()
                expect(terminal.locator("#font-size")).to_have_text("24px")
                for _ in range(18):
                    terminal.get_by_role("button", name="Decrease terminal font").click()
                expect(terminal.locator("#font-size")).to_have_text("10px")
                for _ in range(4):
                    terminal.get_by_role("button", name="Increase terminal font").click()
                expect(terminal.locator("#font-size")).to_have_text("14px")
                passed("Font bounds 10–24, integer steps and fit/resize")
                terminal.evaluate(
                    """window.__clipboardWrites=0;Object.defineProperty(navigator,'clipboard',{configurable:true,value:{readText:()=>Promise.reject(new Error('denied')),writeText:()=>{window.__clipboardWrites++;return Promise.resolve()}}})"""
                )
                terminal.locator(".xterm-helper-textarea").press_sequentially("MOCK_ANSI", delay=30)
                expect(terminal.locator("#terminal")).to_contain_text("ANSI_RED_PROOF")
                assert terminal.evaluate("window.__clipboardWrites") == 0
                assert terminal.locator("#terminal a").count() == 0
                passed(
                    "ANSI rendering and hostile OSC52 / OSC8 output cannot write clipboard or create links"
                )
                terminal.locator(".xterm-helper-textarea").press_sequentially("MOCK_LINES", delay=30)
                expect(terminal.locator("#terminal")).to_contain_text("SCROLLBACK_FINAL_PROOF", timeout=15000)
                terminal.get_by_role("button", name="Search (Ctrl+F)", exact=True).click()
                terminal.locator("#search-term").fill("SCROLLBACK_OLD_CANARY")
                terminal.get_by_role("button", name="Next match", exact=True).click()
                expect(terminal.locator("#search-result")).to_have_text("No match")
                terminal.locator("#search-term").fill("SCROLLBACK_FINAL_PROOF")
                terminal.get_by_role("button", name="Next match", exact=True).click()
                expect(terminal.locator("#search-result")).to_have_text("Match highlighted")
                terminal.get_by_role("button", name="Close search", exact=True).click()
                passed("More than 10,000 output lines trims old scrollback; search covers retained RAM only")
                terminal.locator(".xterm-helper-textarea").press("Control+b")
                terminal.wait_for_timeout(160)
                terminal.locator(".xterm-helper-textarea").press("d")
                terminal.wait_for_timeout(400)
                terminal.locator(".xterm-helper-textarea").press_sequentially(
                    "printf 'UI_TERM:%s\\n' \"$TERM\"", delay=20
                )
                terminal.locator(".xterm-helper-textarea").press("Enter")
                expect(terminal.locator("#terminal")).to_contain_text("UI_TERM:xterm-256color")
                passed("Native tmux detach remains ordinary SSH account shell; TERM xterm-256color")
                assert terminal.evaluate(
                    """()=>{const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);return event.defaultPrevented;}"""
                )
                passed(
                    "Connected beforeunload warning handler requests cancellation (native prompt remains browser-controlled)"
                )
                terminal.evaluate("window.__r1Trace.length=0")
                terminal.get_by_role("button", name="Reconnect", exact=True).click()
                terminal.locator("#dialog-accept").click()
                expect(terminal.locator("#connection-state")).to_have_text("Connected", timeout=15000)
                rd_context = browser.new_context(viewport={"width": 1280, "height": 1000})
                rd_context.add_init_script(
                    path=str(Path(__file__).resolve().parents[1] / "tests/console_mock/browser_lifecycle.js")
                )
                rd = rd_context.new_page()
                login(rd, "uird")
                rd.goto(base + f"/suts/{sut}/connections")
                expect(rd.get_by_role("heading", name="UART", exact=True)).to_be_visible()
                assert rd.get_by_text("Edit inventory", exact=True).count() == 0
                viewer = open_console(rd_context, sut)
                viewer.get_by_role("button", name="Connect", exact=True).click()
                expect(viewer.locator("#effective-mode")).to_have_text("Read-only", timeout=15000)
                expect(viewer.locator("#send-key-button")).to_be_disabled()
                expect(viewer.locator(".xterm-helper-textarea")).not_to_be_focused()
                paste(viewer, "READONLY_CANNOT_TYPE")
                expect(viewer.locator("#console-feedback")).to_contain_text("Read-only")

                def r1_diagnostics():
                    for role, tab in (("writer", terminal), ("viewer", viewer)):
                        print(
                            "R1 lifecycle",
                            role,
                            json.dumps(tab.evaluate("window.__r1Trace || []")),
                            flush=True,
                        )
                    safe_rows = "import sqlite3,json; c=sqlite3.connect('/db/browser.db'); print(json.dumps(c.execute('select id,user_id,state,attachment_generation,close_reason from console_sessions order by id').fetchall()))"
                    rows = json.loads(docker("exec", web, "python", "-c", safe_rows))
                    sanitized = [
                        {
                            "session": f"session-{i}",
                            "rd": f"rd-{r[1]}",
                            "state": r[2],
                            "generation": r[3],
                            "close_reason": r[4],
                        }
                        for i, r in enumerate(rows, 1)
                    ]
                    print("R1 sessions", json.dumps(sanitized), flush=True)

                try:
                    expect(terminal.locator("#participants")).to_contain_text(
                        "2 distinct Web RD", timeout=5000
                    )
                except Exception:
                    r1_diagnostics()
                    raise
                if os.environ.get("SUT_CONSOLE_R1_TRACE") == "1":
                    r1_diagnostics()
                expect(terminal.locator("#shared-warning")).to_be_visible()
                passed(
                    "Nonholder read-only terminal, disabled input/paste/keys, separate RD mapping permission and shared warning"
                )
                assert api(rd, f"/suts/{sut}/claim", "POST", {"duration_minutes": 60})["status"] == 201
                expect(viewer.locator("#console-feedback")).to_contain_text("read-only", timeout=5000)
                viewer.get_by_role("button", name="Reconnect", exact=True).click()
                viewer.locator("#dialog-accept").click()
                expect(viewer.locator("#effective-mode")).to_have_text("Read / Write", timeout=15000)
                expect(viewer.locator(".xterm-helper-textarea")).to_be_focused()
                terminal.locator(".xterm-helper-textarea").press_sequentially("ADMIN_WRITER_PROOF", delay=30)
                viewer.locator(".xterm-helper-textarea").press_sequentially("RD_WRITER_PROOF", delay=30)
                expect(terminal.locator("#terminal")).to_contain_text("RD_WRITER_PROOF")
                expect(viewer.locator("#terminal")).to_contain_text("ADMIN_WRITER_PROOF")
                passed(
                    "Claim-authorized RD reconnect becomes writable; two concurrent authorized UART writers"
                )
                duplicate = open_console(rd_context, sut)
                duplicate.get_by_role("button", name="Connect", exact=True).click()
                expect(duplicate.locator("#connection-state")).to_have_text("Connected", timeout=15000)
                expect(duplicate.locator("#participants")).to_contain_text("2 distinct Web RD", timeout=5000)
                rd.goto(base + "/console/sessions")
                expect(rd.locator("#console-quota")).to_contain_text("2/10")
                expect(rd.locator("#own-sessions")).to_contain_text("UI UART")
                assert rd.get_by_role("button", name="Kill").count() == 0
                passed(
                    "Same-RD duplicate tabs count once as participant, twice in own session inventory without remote kill"
                )
                additional = []
                for _ in range(8):
                    extra = open_console(rd_context, sut)
                    extra.get_by_role("button", name="Connect", exact=True).click()
                    expect(extra.locator("#connection-state")).to_have_text("Connected", timeout=15000)
                    additional.append(extra)
                denied = open_console(rd_context, sut)
                denied.get_by_role("button", name="Connect", exact=True).click()
                expect(denied.locator("#console-feedback")).to_contain_text("All 10", timeout=15000)
                rd.get_by_role("button", name="Refresh sessions", exact=True).click()
                expect(rd.locator("#console-quota")).to_contain_text("10/10")
                for extra in additional:
                    extra.get_by_role("button", name="Disconnect", exact=True).click()
                    extra.close()
                duplicate.get_by_role("button", name="Disconnect", exact=True).click()
                duplicate.close()
                denied.close()
                expect(terminal.locator("#connection-state")).to_have_text("Connected")
                passed("Ten real multi-tab sessions allowed, 11th rejected, own Disconnect preserves peers")
                # Reuse the stable release key from the authenticated coordination projection.
                details = api(rd, f"/suts/{sut}/coordination")["data"]
                usage = details["usage"]
                assert (
                    api(rd, f"/suts/{sut}/release", "POST", {"usage_key": usage["usage_key"]})["status"]
                    == 200
                )
                expect(viewer.locator("#effective-mode")).to_have_text("Read-only", timeout=5000)
                expect(viewer.locator("#send-key-button")).to_be_disabled()
                viewer.get_by_role("button", name="Disconnect", exact=True).click()
                viewer.close()
                rd_context.close()
                passed("Release revalidation downgrades nonholder UX immediately without input replay")
                # Admin pre-save failures keep the original live UART attachment.
                page.goto(base + "/admin/console-clients")
                page.locator("#client-list").get_by_role("button", name="Edit").click()
                page.get_by_label("New / replacement SSH password", exact=True).fill(
                    secrets.token_urlsafe(28)
                )
                page.get_by_role("button", name="Save Client", exact=True).click()
                expect(page.locator("#console-feedback")).to_contain_text(
                    "authentication failed", timeout=15000
                )
                expect(page.locator("#client-password")).to_have_value("")
                expect(terminal.locator("#connection-state")).to_have_text("Connected")
                passed(
                    "Failed credential replacement preserves old live connection and clears submitted secret"
                )
                page.get_by_label("Lab", exact=True).select_option(label="Other Mock Lab")
                page.get_by_role("button", name="Save Client", exact=True).click()
                expect(page.locator("#console-feedback")).to_contain_text("Unbind retained")
                page.get_by_role("button", name="Reload Clients", exact=True).click()
                expect(page.get_by_role("button", name="Reload Clients", exact=True)).to_be_enabled()
                expect(page.get_by_label("Lab", exact=True)).to_have_value("1")
                page.get_by_label("Authentication method", exact=True).select_option("private_key")
                page.get_by_label("New / replacement private key", exact=True).fill(fixture["private_key"])
                page.get_by_label("Private-key passphrase (if needed)", exact=True).fill(
                    fixture["passphrase"]
                )
                page.get_by_role("button", name="Save Client", exact=True).click()
                try:
                    expect(page.get_by_role("heading", name="Confirm affected sessions")).to_be_visible(
                        timeout=15000
                    )
                except Exception:
                    raise
                page.locator("#dialog-accept").click()
                expect(page.locator("#console-feedback")).to_contain_text("Client saved", timeout=15000)
                expect(page.locator("#client-key")).to_have_value("")
                expect(page.locator("#client-passphrase")).to_have_value("")
                expect(terminal.locator("#connection-state")).to_have_text("Disconnected", timeout=5000)
                passed(
                    "Bound Client Lab move refusal and validated encrypted-private-key rotation with affected-session revocation"
                )
                terminal.get_by_role("button", name="Connect", exact=True).click()
                expect(terminal.locator("#connection-state")).to_have_text("Connected", timeout=15000)
                # Grant management is available to Lab Admin independently of account management.
                lab_context = browser.new_context()
                lab_page = lab_context.new_page()
                login(lab_page, "uilab")
                count_code = "import sqlite3,json; c=sqlite3.connect('/db/browser.db'); print(json.dumps({t:c.execute('select count(*) from '+t).fetchone()[0] for t in ['current_usages','queue_entries','reservations','usage_histories','notifications']}))"
                before_grants = docker("exec", web, "python", "-c", count_code)
                lab_page.goto(base + "/admin/console-grants")
                lab_page.get_by_label("SUT", exact=True).select_option(label="UI Maintenance · maintenance")
                lab_page.get_by_label("RD", exact=True).select_option(label="Synthetic uird · Mock")
                lab_page.get_by_role("button", name="Grant Console access", exact=True).click()
                expect(lab_page.locator("#grant-list")).to_contain_text("Synthetic uird")
                lab_page.get_by_label("RD", exact=True).select_option(label="Synthetic uipeer · Mock")
                lab_page.get_by_role("button", name="Grant Console access", exact=True).click()
                expect(lab_page.locator("#grant-list")).to_contain_text("Synthetic uipeer")
                first = lab_page.locator("#grant-list tr").filter(has_text="Synthetic uird")
                first.locator("select").select_option(index=0)
                first.get_by_role("button", name="Extend", exact=True).click()
                expect(lab_page.locator("#grant-list")).to_contain_text("Synthetic uird")
                first = lab_page.locator("#grant-list tr").filter(has_text="Synthetic uird")
                first.get_by_role("button", name="Revoke", exact=True).click()
                lab_page.locator("#dialog-accept").click()
                expect(lab_page.locator("#grant-list tr").filter(has_text="Synthetic uird")).to_contain_text(
                    "revoked"
                )
                expect(
                    lab_page.locator("#grant-list tr").filter(has_text="Synthetic uipeer")
                ).to_contain_text("active")
                assert docker("exec", web, "python", "-c", count_code) == before_grants
                lab_context.close()
                passed(
                    "Lab Admin named independent maintenance grants, bounded extension and confirmed scoped revoke"
                )
                # Mapping clear previews and stale versions remain authoritative at the UI.
                settings = context.new_page()
                settings.goto(base + f"/suts/{sut}/connections")
                settings.get_by_role("button", name="Clear UART", exact=True).click()
                expect(settings.get_by_role("heading", name="Confirm affected sessions")).to_be_visible()
                settings.get_by_role("button", name="Cancel", exact=True).click()
                expect(terminal.locator("#connection-state")).to_have_text("Connected")
                settings.get_by_role("button", name="Clear UART", exact=True).click()
                settings.locator("#dialog-accept").click()
                expect(settings.locator("#uart-summary")).to_have_text("Not Configured")
                expect(terminal.locator("#connection-state")).to_have_text("Disconnected", timeout=5000)
                settings.get_by_label("Console Client (same Lab)", exact=True).select_option(
                    label="Synthetic SSH Client · " + fixture["host"] + ":22"
                )
                settings.get_by_label("Existing tmux session", exact=True).fill("existing")
                settings.get_by_role("button", name="Save UART", exact=True).click()
                expect(settings.locator("#console-feedback")).to_contain_text("Connection saved")
                stale = context.new_page()
                stale.goto(base + f"/suts/{sut}/connections")
                settings.get_by_role("button", name="Save UART", exact=True).click()
                expect(settings.locator("#uart-summary")).to_contain_text("revision 4")
                stale.get_by_role("button", name="Save UART", exact=True).click()
                expect(stale.locator("#console-feedback")).to_contain_text("changed while")
                stale.close()
                settings.close()
                passed("Independent mapping clear/impact cancel/confirm/history and stale-update handling")
                # Deliberate host-key replacement uses independent synthetic fixture evidence.
                terminal.get_by_role("button", name="Connect", exact=True).click()
                expect(terminal.locator("#connection-state")).to_have_text("Connected", timeout=15000)
                direct = open_console(context, sut)
                direct.locator("#console-mode").select_option("bmc")
                direct.get_by_role("button", name="Connect", exact=True).click()
                expect(direct.locator("#bmc-auth")).to_be_visible(timeout=15000)
                direct.get_by_label("BMC username", exact=True).fill(fixture["username"])
                direct.get_by_label("BMC password", exact=True).fill(fixture["password"])
                direct.get_by_role("button", name="Authenticate", exact=True).click()
                expect(direct.locator("#connection-state")).to_have_text("Connected", timeout=15000)
                rotate = """import asyncssh,os,signal; from pathlib import Path; key=asyncssh.generate_private_key('ssh-ed25519'); Path('/etc/ssh/ssh_host_ed25519_key').write_bytes(key.export_private_key()); os.chmod('/etc/ssh/ssh_host_ed25519_key',0o600); Path('/etc/ssh/ssh_host_ed25519_key.pub').write_bytes(key.export_public_key()); os.kill(int(Path('/run/mock-sshd.pid').read_text()),signal.SIGHUP); print(key.get_fingerprint('sha256'))"""
                fingerprint = docker("exec", name + "-ssh", "python", "-c", rotate).strip()
                time.sleep(0.3)
                terminal.get_by_role("button", name="Review Host Key", exact=True).click()
                expect(terminal.locator("#dialog-text")).to_contain_text(fingerprint, timeout=15000)
                expect(terminal.locator("#dialog-text")).not_to_contain_text("Previous: Unknown")
                expect(terminal.locator("#dialog-accept")).to_be_disabled()
                terminal.locator("#dialog-ack").check()
                terminal.locator("#dialog-accept").click()
                expect(terminal.locator("#connection-state")).to_have_text("Disconnected", timeout=5000)
                expect(direct.locator("#connection-state")).to_have_text("Connected")
                direct.get_by_role("button", name="Review Host Key", exact=True).click()
                expect(direct.locator("#dialog-text")).to_contain_text(fingerprint, timeout=15000)
                direct.locator("#dialog-ack").check()
                direct.locator("#dialog-accept").click()
                expect(direct.locator("#connection-state")).to_have_text("Disconnected", timeout=5000)
                direct.close()
                passed(
                    "Changed Client/BMC Host Keys show independent old/new fingerprints, require acknowledgement, and revoke only their transport"
                )
                # No terminal/font/credential persistence, including reload.
                contents = terminal.evaluate(
                    """()=>({local:Object.values(localStorage),session:Object.values(sessionStorage)})"""
                )
                forbidden = [
                    fixture["password"],
                    fixture["private_key"],
                    fixture["passphrase"],
                    data["web_password"],
                    "BROWSER_UART_PROOF",
                    "PASTE_SINGLE_PROOF",
                    "MULTILINE_TWO",
                ]
                assert all(canary not in json.dumps(contents) for canary in forbidden)
                terminal.reload()
                expect(terminal.locator("#font-size")).to_have_text("14px")
                expect(terminal.locator("#connection-state")).to_have_text("Not Connected")
                expect(terminal.locator("#terminal")).not_to_contain_text("BROWSER_UART_PROOF")
                assert terminal.evaluate(
                    "async()=>!indexedDB.databases || (await indexedDB.databases()).length===0"
                )
                passed(
                    "Reload drops RAM buffer/font preference; credentials and terminal canaries absent from browser storage / IndexedDB"
                )
                # Inspect only boolean/counters outside the synthetic DB; never print a dump.
                scan = """import sqlite3,json,sys; values=json.load(sys.stdin); c=sqlite3.connect('/db/browser.db'); dump='\\n'.join(c.iterdump()); assert not any(v in dump for v in values); assert c.execute('pragma integrity_check').fetchone()[0]=='ok'; assert not c.execute('pragma foreign_key_check').fetchall(); print('PASS: DB canary exclusion, integrity and foreign keys')"""
                print(docker("exec", "-i", web, "python", "-c", scan, data=json.dumps(forbidden)), end="")
                passed(
                    "Sensitive Client/BMC/terminal canaries absent from synthetic SQLite, integrity/FKs intact"
                )
                # Failure and missing-configuration UI never creates remote sessions.
                settings = context.new_page()
                settings.goto(base + f"/suts/{sut}/connections")
                settings.get_by_label("Existing tmux session", exact=True).fill("missing")
                settings.get_by_role("button", name="Save UART", exact=True).click()
                expect(settings.locator("#console-feedback")).to_contain_text("Connection saved")
                terminal.get_by_role("button", name="Connect", exact=True).click()
                expect(terminal.locator("#connection-state")).to_have_text("Failed", timeout=15000)
                expect(terminal.locator("#console-feedback")).to_contain_text("missing or inaccessible")
                expect(terminal.get_by_role("button", name="Retry", exact=True)).to_be_visible()
                expect(
                    terminal.get_by_role("link", name="Edit Connection / History", exact=True)
                ).to_be_visible()
                terminal.wait_for_timeout(300)
                expect(terminal.locator("#connection-state")).to_have_text("Failed")
                settings.get_by_label("Existing tmux session", exact=True).fill("existing")
                settings.get_by_role("button", name="Save UART", exact=True).click()
                expect(settings.locator("#console-feedback")).to_contain_text("Connection saved")
                terminal.get_by_role("button", name="Retry", exact=True).click()
                expect(terminal.locator("#connection-state")).to_have_text("Connected", timeout=15000)
                terminal.get_by_role("button", name="Disconnect", exact=True).click()
                passed(
                    "Missing existing tmux gives Failed / Retry / Edit, no automatic creation or retry; corrected mapping reconnects"
                )
                # Only unbound Clients can move; retain identity/credential through move/disable.
                settings.get_by_role("button", name="Clear UART", exact=True).click()
                expect(settings.locator("#uart-summary")).to_have_text("Not Configured")
                page.goto(base + "/admin/console-clients")
                page.locator("#client-list").get_by_role("button", name="Edit").click()
                page.get_by_label("Lab", exact=True).select_option(label="Other Mock Lab")
                page.get_by_role("button", name="Save Client", exact=True).click()
                expect(page.locator("#client-list")).to_contain_text("Other Mock Lab")
                settings.get_by_role("button", name="Reload settings", exact=True).click()
                expect(settings.locator("#client-id")).not_to_contain_text("Synthetic SSH Client")
                page.get_by_label("Lab", exact=True).select_option(label="Browser Mock Lab")
                page.get_by_role("button", name="Save Client", exact=True).click()
                expect(page.locator("#client-list")).to_contain_text("Browser Mock Lab")
                settings.get_by_role("button", name="Reload settings", exact=True).click()
                expect(settings.locator("#client-id")).to_contain_text("Synthetic SSH Client")
                settings.get_by_label("Console Client (same Lab)", exact=True).select_option(
                    label="Synthetic SSH Client · " + fixture["host"] + ":22"
                )
                settings.get_by_label("Existing tmux session", exact=True).fill("existing")
                settings.get_by_role("button", name="Save UART", exact=True).click()
                expect(settings.locator("#console-feedback")).to_contain_text("Connection saved")
                page.get_by_role("button", name="Disable Client", exact=True).click()
                expect(page.locator("#console-feedback")).to_contain_text("Client disabled")
                settings.get_by_role("button", name="Reload settings", exact=True).click()
                expect(settings.locator("#uart-summary")).to_contain_text("Client Disabled")
                terminal.get_by_role("button", name="Connect", exact=True).click()
                expect(terminal.locator("#console-feedback")).to_contain_text("Client is disabled")
                page.get_by_role("button", name="Enable Client", exact=True).click()
                expect(page.locator("#console-feedback")).to_contain_text("Client enabled")
                terminal.get_by_role("button", name="Retry", exact=True).click()
                expect(terminal.locator("#connection-state")).to_have_text("Connected", timeout=15000)
                terminal.get_by_role("button", name="Disconnect", exact=True).click()
                settings.close()
                passed(
                    "Unbound Lab move preserves Client; same-Lab choices, retained disabled mapping and reenable with existing credentials"
                )
                peer = next(item["id"] for item in inventory if item["name"] == "UI Peer")
                page.goto(base + f"/suts/{peer}")
                expect(page.locator("#console-detail-summary")).to_contain_text("UART: Not Configured")
                expect(page.locator("#console-detail-summary")).to_contain_text("BMC SSH: Not Configured")
                with context.expect_page() as opening:
                    page.get_by_role("link", name="Open Remote Console", exact=True).click()
                empty = opening.value
                expect(empty.locator("#endpoint-summary")).to_contain_text("Not Configured")
                assert empty.evaluate("window.opener===null")
                empty.get_by_role("button", name="Connect", exact=True).click()
                expect(empty.locator("#connection-state")).to_have_text("Failed")
                expect(empty.locator("#console-feedback")).to_contain_text("Not Configured")
                empty.locator("#console-mode").select_option("bmc")
                expect(empty.locator("#endpoint-summary")).to_contain_text("Not Configured")
                empty.close()
                passed(
                    "Detail configuration summaries and separate noopener tab; both missing mappings stay Not Configured"
                )
                terminal.close()
                assert not errors, "browser script errors"
                browser.close()
                print(f"PASS: {len(checks)} Chromium Console checks (actual mock SSH/tmux)", flush=True)
        except Exception as error:
            failed_line = None
            traceback = error.__traceback__
            while traceback:
                if traceback.tb_frame.f_code.co_filename == __file__:
                    failed_line = traceback.tb_lineno
                traceback = traceback.tb_next
            # Playwright exception call logs can reflect fill inputs; never emit them.
            raise AssertionError(
                f"Console Chromium validation failed at harness line {failed_line}; last completed stage: "
                + (checks[-1] if "checks" in locals() and checks else "startup")
            ) from None
        finally:
            subprocess.run(
                ["docker", "--host=unix:///var/run/docker.sock", "rm", "-f", web], capture_output=True
            )
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
