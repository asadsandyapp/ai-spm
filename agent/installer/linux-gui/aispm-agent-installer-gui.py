#!/usr/bin/env python3
"""AI-SPM enterprise guided installer (Linux) — Tkinter wizard.

Reads enrollment.env beside this script (or the zip extract root), then runs
install-agent.sh via pkexec/sudo so employees never type org tokens.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

HERE = Path(__file__).resolve().parent


def load_enrollment(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        raise FileNotFoundError(str(path))
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip().strip('"').strip("'")
    required = ("AISPM_GATEWAY_URL", "AISPM_ORG_ID", "AISPM_ORG_TOKEN")
    missing = [k for k in required if not env.get(k)]
    if missing:
        raise ValueError(f"enrollment.env missing: {', '.join(missing)}")
    return env


class InstallerApp(tk.Tk):
    def __init__(self, enrollment: dict[str, str]) -> None:
        super().__init__()
        self.enrollment = enrollment
        self.title("AI-SPM Endpoint Agent Setup")
        self.geometry("640x480")
        self.minsize(560, 420)
        self.configure(bg="#f4f6f8")
        self.step = 0
        self.opts = {
            "service": tk.BooleanVar(value=True),
            "ca": tk.BooleanVar(value=True),
            "extensions": tk.BooleanVar(value=True),
        }
        self._build_style()
        self.container = ttk.Frame(self, padding=24)
        self.container.pack(fill=tk.BOTH, expand=True)
        self._show_step(0)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("Helvetica", 18, "bold"), background="#f4f6f8")
        style.configure("Body.TLabel", font=("Helvetica", 11), background="#f4f6f8", foreground="#334155")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Primary.TButton", font=("Helvetica", 11, "bold"), padding=8)

    def _clear(self) -> None:
        for w in self.container.winfo_children():
            w.destroy()

    def _show_step(self, step: int) -> None:
        self.step = step
        self._clear()
        {
            0: self._welcome,
            1: self._organization,
            2: self._components,
            3: self._privilege,
            4: self._progress,
            5: self._done,
        }[step]()

    def _nav(self, back=None, next_label="Continue", next_cmd=None, disable_next=False):
        bar = ttk.Frame(self.container)
        bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(16, 0))
        if back is not None:
            ttk.Button(bar, text="Back", command=back).pack(side=tk.LEFT)
        btn = ttk.Button(bar, text=next_label, style="Primary.TButton", command=next_cmd)
        btn.pack(side=tk.RIGHT)
        if disable_next:
            btn.state(["disabled"])

    def _welcome(self) -> None:
        ttk.Label(self.container, text="AI-SPM Endpoint Agent", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            self.container,
            text=(
                "This wizard installs the enterprise endpoint agent on this computer.\n"
                "It registers with your organization gateway, enables transparent API\n"
                "protection, and deploys the managed browser extension for ChatGPT,\n"
                "Claude, and Gemini."
            ),
            style="Body.TLabel",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(12, 0))
        self._nav(next_cmd=lambda: self._show_step(1))

    def _organization(self) -> None:
        ttk.Label(self.container, text="Organization", style="Title.TLabel").pack(anchor=tk.W)
        card = ttk.Frame(self.container, style="Card.TFrame", padding=16)
        card.pack(fill=tk.X, pady=(12, 0))
        rows = [
            ("Name", self.enrollment.get("AISPM_ORG_NAME", "(from enrollment)")),
            ("Gateway", self.enrollment["AISPM_GATEWAY_URL"]),
            ("Org ID", self.enrollment["AISPM_ORG_ID"]),
            ("Token", self.enrollment["AISPM_ORG_TOKEN"][:8] + "…" + self.enrollment["AISPM_ORG_TOKEN"][-4:]),
        ]
        for label, value in rows:
            row = ttk.Frame(card)
            row.pack(fill=tk.X, pady=4)
            ttk.Label(row, text=label, width=12, style="Body.TLabel").pack(side=tk.LEFT)
            ttk.Label(row, text=value, style="Body.TLabel").pack(side=tk.LEFT)
        ttk.Label(
            self.container,
            text="Credentials come from enrollment.env — employees do not type secrets.",
            style="Body.TLabel",
        ).pack(anchor=tk.W, pady=(12, 0))
        self._nav(back=lambda: self._show_step(0), next_cmd=lambda: self._show_step(2))

    def _components(self) -> None:
        ttk.Label(self.container, text="Components", style="Title.TLabel").pack(anchor=tk.W)
        card = ttk.Frame(self.container, style="Card.TFrame", padding=16)
        card.pack(fill=tk.X, pady=(12, 0))
        ttk.Checkbutton(card, text="Agent service (systemd ai-spm-agent)", variable=self.opts["service"]).pack(anchor=tk.W)
        ttk.Checkbutton(card, text="Local MITM CA trust (API host inspection)", variable=self.opts["ca"]).pack(anchor=tk.W, pady=(8, 0))
        ttk.Checkbutton(
            card,
            text="Managed browser extensions (Chrome / Firefox policies)",
            variable=self.opts["extensions"],
        ).pack(anchor=tk.W, pady=(8, 0))
        self._nav(back=lambda: self._show_step(1), next_cmd=lambda: self._show_step(3))

    def _privilege(self) -> None:
        ttk.Label(self.container, text="Administrator privileges", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            self.container,
            text=(
                "Installation requires administrator rights to install the system service,\n"
                "CA certificates, firewall rules, and browser enterprise policies.\n\n"
                "Click Install to continue — you will be prompted for your password."
            ),
            style="Body.TLabel",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(12, 0))
        self._nav(
            back=lambda: self._show_step(2),
            next_label="Install",
            next_cmd=lambda: self._show_step(4),
        )

    def _progress(self) -> None:
        ttk.Label(self.container, text="Installing…", style="Title.TLabel").pack(anchor=tk.W)
        self.log = tk.Text(self.container, height=16, wrap=tk.WORD, font=("Courier", 10))
        self.log.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        self._nav(next_label="Please wait…", disable_next=True)
        threading.Thread(target=self._run_install, daemon=True).start()

    def _append(self, line: str) -> None:
        self.log.insert(tk.END, line + "\n")
        self.log.see(tk.END)

    def _run_install(self) -> None:
        script = HERE / "install-agent.sh"
        if not script.is_file():
            self.after(0, lambda: messagebox.showerror("Install failed", "install-agent.sh missing from package."))
            return
        env = os.environ.copy()
        env.update(self.enrollment)
        if not self.opts["extensions"].get():
            env["AISPM_SKIP_EXTENSIONS"] = "1"
        cmd = self._elevate_cmd(script)
        self.after(0, lambda: self._append("$ " + " ".join(cmd)))
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                cwd=str(HERE),
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                text = line.rstrip()
                self.after(0, lambda t=text: self._append(t))
            code = proc.wait()
        except Exception as exc:  # noqa: BLE001
            self.after(0, lambda: messagebox.showerror("Install failed", str(exc)))
            return
        if code != 0:
            self.after(
                0,
                lambda: messagebox.showerror("Install failed", f"Installer exited with code {code}."),
            )
            self.after(0, lambda: self._show_step(3))
            return
        self.after(0, lambda: self._show_step(5))

    def _elevate_cmd(self, script: Path) -> list[str]:
        # Absolute bash + full PATH — pkexec omits /usr/sbin and bare "bash" can 127.
        bash = shutil.which("bash") or "/bin/bash"
        path = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        env_args = [f"PATH={path}", *[f"{k}={v}" for k, v in self.enrollment.items()]]
        argv = [bash, str(script.resolve())]
        if shutil.which("pkexec"):
            return ["pkexec", "env", *env_args, *argv]
        if shutil.which("sudo"):
            return ["sudo", "-E", "env", *env_args, *argv]
        return argv

    def _done(self) -> None:
        ttk.Label(self.container, text="Installation complete", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            self.container,
            text=(
                "The agent is registering with your organization gateway.\n"
                "Ask your admin to confirm this device shows Online under Agent Fleet.\n\n"
                f"Gateway: {self.enrollment['AISPM_GATEWAY_URL']}"
            ),
            style="Body.TLabel",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(12, 0))
        self._nav(next_label="Close", next_cmd=self.destroy)


def main() -> int:
    candidates = [
        HERE / "enrollment.env",
        Path.cwd() / "enrollment.env",
    ]
    enrollment_path = next((p for p in candidates if p.is_file()), None)
    if enrollment_path is None:
        messagebox.showerror(
            "AI-SPM Installer",
            "enrollment.env not found.\n\n"
            "Download the organization package from Admin → Download Agent.",
        )
        return 1
    try:
        enrollment = load_enrollment(enrollment_path)
    except (OSError, ValueError) as exc:
        messagebox.showerror("AI-SPM Installer", str(exc))
        return 1
    app = InstallerApp(enrollment)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
