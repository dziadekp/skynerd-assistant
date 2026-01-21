"""
CLI interface for SkyNerd Assistant.

Commands:
- chat: Chat with the AI assistant
- status: Show current status
- remind: Create a reminder
- daemon: Start/stop/status of the background daemon
- install: Install the daemon as a system service
"""

import asyncio
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

from .config import load_settings
from .clients.skynerd import SkyNerdClient
from .clients.ollama import OllamaClient
from .daemon import AssistantDaemon

app = typer.Typer(
    name="skynerd-assistant",
    help="Local AI assistant for SkyNerd Control",
    no_args_is_help=True,
)
console = Console()


def get_settings():
    """Load settings with error handling."""
    try:
        return load_settings()
    except Exception as e:
        console.print(f"[red]Error loading settings:[/red] {e}")
        console.print("Run [bold]skynerd-assistant init[/bold] to create a config file.")
        raise typer.Exit(1)


# ============================================================================
# Chat Command
# ============================================================================

@app.command()
def chat(
    message: str = typer.Argument(..., help="Message to send to the AI assistant"),
    context: bool = typer.Option(True, "--context/--no-context", help="Include work context"),
):
    """
    Chat with the AI assistant.

    Examples:
        skynerd-assistant chat "What's my priority today?"
        skynerd-assistant chat "Summarize my unread emails"
        skynerd-assistant chat "How many tasks are overdue?"
    """
    settings = get_settings()

    async def _chat():
        async with SkyNerdClient(settings.api.base_url, settings.api.api_key) as client:
            # Get context if requested
            context_data = None
            if context:
                try:
                    context_data = await client.get_status()
                except Exception:
                    pass

            # Build prompt with context
            prompt = message
            if context_data:
                prompt = _build_contextual_prompt(message, context_data)

            # Chat with Ollama
            if settings.ollama.enabled:
                ollama = OllamaClient(
                    base_url=settings.ollama.base_url,
                    model=settings.ollama.model,
                )
                try:
                    # Stream response
                    console.print(Panel("[bold]Assistant[/bold]"))
                    async for chunk in ollama.chat_stream(prompt):
                        console.print(chunk, end="")
                    console.print()  # Newline at end
                except Exception as e:
                    console.print(f"[red]Error:[/red] {e}")
                finally:
                    await ollama.close()
            else:
                console.print("[yellow]Ollama is not enabled. Enable it in your config.[/yellow]")

    asyncio.run(_chat())


def _build_contextual_prompt(message: str, context: dict) -> str:
    """Build a prompt with work context."""
    parts = [
        "You are a helpful work assistant. Here is the current work context:\n",
    ]

    email = context.get("email", {})
    if email:
        parts.append(f"- Unread emails: {email.get('unread_count', 0)}")
        parts.append(f"- High priority emails: {email.get('high_priority_count', 0)}")

    tasks = context.get("tasks", {})
    if tasks:
        parts.append(f"- Overdue tasks: {tasks.get('overdue_count', 0)}")
        parts.append(f"- Tasks due today: {tasks.get('due_today_count', 0)}")

    calendar = context.get("calendar", {})
    if calendar:
        parts.append(f"- Events today: {calendar.get('today_count', 0)}")
        parts.append(f"- Next event: {calendar.get('next_event', 'None')}")

    reminders = context.get("reminders", {})
    if reminders:
        parts.append(f"- Pending reminders: {reminders.get('pending_count', 0)}")

    parts.append(f"\nUser's question: {message}")

    return "\n".join(parts)


# ============================================================================
# Status Command
# ============================================================================

@app.command()
def status():
    """
    Show current status from SkyNerd Control.

    Displays unread emails, overdue tasks, upcoming events, and reminders.
    """
    settings = get_settings()

    async def _status():
        async with SkyNerdClient(settings.api.base_url, settings.api.api_key) as client:
            try:
                data = await client.get_status()
                _display_status(data)
            except Exception as e:
                console.print(f"[red]Error fetching status:[/red] {e}")
                raise typer.Exit(1)

    asyncio.run(_status())


def _display_status(data: dict):
    """Display status data in a formatted way."""
    console.print()

    # Email section
    email = data.get("email", {})
    email_table = Table(title="📧 Email", show_header=False, box=None)
    email_table.add_row("Unread", str(email.get("unread_count", 0)))
    email_table.add_row("High Priority", f"[red]{email.get('high_priority_count', 0)}[/red]")
    console.print(email_table)
    console.print()

    # Tasks section
    tasks = data.get("tasks", {})
    task_table = Table(title="✅ Tasks", show_header=False, box=None)
    overdue = tasks.get("overdue_count", 0)
    task_table.add_row("Overdue", f"[red]{overdue}[/red]" if overdue > 0 else "0")
    task_table.add_row("Due Today", str(tasks.get("due_today_count", 0)))
    task_table.add_row("Due This Week", str(tasks.get("due_this_week_count", 0)))
    console.print(task_table)
    console.print()

    # Calendar section
    calendar = data.get("calendar", {})
    cal_table = Table(title="📅 Calendar", show_header=False, box=None)
    cal_table.add_row("Events Today", str(calendar.get("today_count", 0)))
    next_event = calendar.get("next_event")
    if next_event:
        cal_table.add_row("Next Event", next_event)
    console.print(cal_table)
    console.print()

    # Reminders section
    reminders = data.get("reminders", {})
    reminder_table = Table(title="🔔 Reminders", show_header=False, box=None)
    reminder_table.add_row("Pending", str(reminders.get("pending_count", 0)))
    reminder_table.add_row("Due Soon", str(reminders.get("due_soon_count", 0)))
    console.print(reminder_table)
    console.print()

    # Timestamp
    console.print(f"[dim]Updated: {data.get('timestamp', 'Unknown')}[/dim]")


# ============================================================================
# Remind Command
# ============================================================================

@app.command()
def remind(
    message: str = typer.Argument(..., help="Reminder message"),
    at: str = typer.Option(None, "--at", "-a", help="Time for reminder (e.g., '3pm', '15:00', 'tomorrow 9am')"),
    in_minutes: int = typer.Option(None, "--in", "-i", help="Minutes from now"),
):
    """
    Create a reminder.

    Examples:
        skynerd-assistant remind "Call John" --at "3pm"
        skynerd-assistant remind "Review PR" --in 30
        skynerd-assistant remind "Team standup" --at "tomorrow 9am"
    """
    settings = get_settings()

    # Parse time
    due_at = _parse_reminder_time(at, in_minutes)
    if not due_at:
        console.print("[red]Error: Specify either --at or --in[/red]")
        raise typer.Exit(1)

    async def _remind():
        async with SkyNerdClient(settings.api.base_url, settings.api.api_key) as client:
            try:
                result = await client.create_reminder(message, due_at.isoformat())
                console.print(f"[green]✓[/green] Reminder created: {message}")
                console.print(f"  Due at: {due_at.strftime('%Y-%m-%d %H:%M')}")
            except Exception as e:
                console.print(f"[red]Error creating reminder:[/red] {e}")
                raise typer.Exit(1)

    asyncio.run(_remind())


def _parse_reminder_time(at: str | None, in_minutes: int | None) -> datetime | None:
    """Parse reminder time from various formats."""
    now = datetime.now()

    if in_minutes:
        return now + timedelta(minutes=in_minutes)

    if not at:
        return None

    at_lower = at.lower().strip()

    # Handle "in X minutes/hours"
    if at_lower.startswith("in "):
        parts = at_lower[3:].split()
        if len(parts) >= 2:
            try:
                amount = int(parts[0])
                unit = parts[1]
                if "min" in unit:
                    return now + timedelta(minutes=amount)
                elif "hour" in unit or unit == "hr":
                    return now + timedelta(hours=amount)
            except ValueError:
                pass

    # Handle "tomorrow" prefix
    tomorrow = False
    if at_lower.startswith("tomorrow"):
        tomorrow = True
        at_lower = at_lower.replace("tomorrow", "").strip()
        if not at_lower:
            # Just "tomorrow" - default to 9am
            return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)

    # Parse time formats
    time_formats = [
        "%I%p",      # 3pm
        "%I:%M%p",   # 3:30pm
        "%H:%M",     # 15:00
        "%I %p",     # 3 pm
        "%I:%M %p",  # 3:30 pm
    ]

    for fmt in time_formats:
        try:
            parsed = datetime.strptime(at_lower, fmt)
            result = now.replace(
                hour=parsed.hour,
                minute=parsed.minute,
                second=0,
                microsecond=0,
            )
            if tomorrow:
                result += timedelta(days=1)
            elif result <= now:
                # If time has passed today, assume tomorrow
                result += timedelta(days=1)
            return result
        except ValueError:
            continue

    console.print(f"[yellow]Could not parse time: {at}[/yellow]")
    return None


# ============================================================================
# Daemon Commands
# ============================================================================

daemon_app = typer.Typer(help="Manage the background daemon")
app.add_typer(daemon_app, name="daemon")


@daemon_app.command("start")
def daemon_start(
    foreground: bool = typer.Option(False, "--foreground", "-f", help="Run in foreground"),
):
    """
    Start the background daemon.

    By default, starts in background mode. Use --foreground to run interactively.
    """
    if foreground:
        console.print("[bold]Starting SkyNerd Assistant daemon (foreground)...[/bold]")
        from .daemon import main
        main()
    else:
        console.print("[bold]Starting SkyNerd Assistant daemon (background)...[/bold]")
        # Start as background process
        if sys.platform == "win32":
            # Windows: use pythonw for background
            subprocess.Popen(
                [sys.executable.replace("python.exe", "pythonw.exe"), "-m", "skynerd_assistant", "daemon", "start", "-f"],
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            )
        else:
            # Unix: fork and detach
            subprocess.Popen(
                [sys.executable, "-m", "skynerd_assistant", "daemon", "start", "-f"],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        console.print("[green]✓[/green] Daemon started in background")


@daemon_app.command("stop")
def daemon_stop():
    """Stop the background daemon."""
    console.print("[bold]Stopping SkyNerd Assistant daemon...[/bold]")
    # This would typically use a PID file or signal
    # For now, suggest manual termination
    if sys.platform == "win32":
        console.print("Use Task Manager to stop 'pythonw.exe' or 'python.exe' running skynerd_assistant")
    else:
        console.print("Use: pkill -f 'skynerd_assistant daemon'")


@daemon_app.command("status")
def daemon_status():
    """Show daemon status."""
    settings = get_settings()

    # Check if daemon is running by looking for PID file or process
    console.print("[bold]Daemon Status[/bold]")
    console.print()

    # Display config
    console.print(f"Config file: {settings.config_path}")
    console.print(f"Data directory: {settings.data_dir}")
    console.print(f"API URL: {settings.api.base_url}")
    console.print(f"Ollama enabled: {settings.ollama.enabled}")
    console.print(f"Voice enabled: {settings.voice.enabled}")
    console.print()

    # Check if log file exists and show recent entries
    log_file = settings.data_dir / "daemon.log"
    if log_file.exists():
        console.print("[bold]Recent log entries:[/bold]")
        with open(log_file) as f:
            lines = f.readlines()
            for line in lines[-10:]:
                console.print(f"  {line.rstrip()}")


# ============================================================================
# Install Command
# ============================================================================

@app.command()
def install(
    windows: bool = typer.Option(False, "--windows", help="Install for Windows Task Scheduler"),
    macos: bool = typer.Option(False, "--macos", help="Install for macOS launchd"),
    linux: bool = typer.Option(False, "--linux", help="Install for Linux systemd"),
):
    """
    Install the daemon as a system service.

    Automatically starts on login.
    """
    if not any([windows, macos, linux]):
        # Auto-detect platform
        if sys.platform == "win32":
            windows = True
        elif sys.platform == "darwin":
            macos = True
        else:
            linux = True

    if windows:
        _install_windows()
    elif macos:
        _install_macos()
    elif linux:
        _install_linux()


def _install_windows():
    """Install as Windows Task Scheduler task."""
    console.print("[bold]Installing for Windows Task Scheduler...[/bold]")

    import getpass
    username = getpass.getuser()
    python_path = sys.executable.replace("python.exe", "pythonw.exe")

    xml_content = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>SkyNerd Assistant - Local AI personal assistant</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{username}</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{username}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  </Settings>
  <Actions>
    <Exec>
      <Command>{python_path}</Command>
      <Arguments>-m skynerd_assistant daemon start -f</Arguments>
    </Exec>
  </Actions>
</Task>'''

    # Save XML file
    task_file = Path.home() / ".skynerd" / "skynerd-assistant.xml"
    task_file.parent.mkdir(parents=True, exist_ok=True)
    task_file.write_text(xml_content, encoding="utf-16")

    console.print(f"Created task file: {task_file}")

    # Register with Task Scheduler
    try:
        subprocess.run(
            ["schtasks", "/create", "/tn", "SkyNerdAssistant", "/xml", str(task_file), "/f"],
            check=True,
            capture_output=True,
        )
        console.print("[green]✓[/green] Task registered with Windows Task Scheduler")
        console.print("The daemon will start automatically on login.")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error registering task:[/red] {e.stderr.decode()}")
        console.print(f"You can manually import {task_file} via Task Scheduler")


def _install_macos():
    """Install as macOS launchd agent."""
    console.print("[bold]Installing for macOS launchd...[/bold]")

    plist_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.skynerd.assistant</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>-m</string>
        <string>skynerd_assistant</string>
        <string>daemon</string>
        <string>start</string>
        <string>-f</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{Path.home()}/.skynerd/daemon.out.log</string>
    <key>StandardErrorPath</key>
    <string>{Path.home()}/.skynerd/daemon.err.log</string>
</dict>
</plist>'''

    # Save plist file
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.skynerd.assistant.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist_content)

    console.print(f"Created plist: {plist_path}")

    # Load the agent
    try:
        subprocess.run(["launchctl", "load", str(plist_path)], check=True)
        console.print("[green]✓[/green] Agent loaded with launchd")
        console.print("The daemon will start automatically on login.")
    except subprocess.CalledProcessError as e:
        console.print(f"[yellow]Note:[/yellow] Run 'launchctl load {plist_path}' to start")


def _install_linux():
    """Install as Linux systemd user service."""
    console.print("[bold]Installing for Linux systemd...[/bold]")

    service_content = f'''[Unit]
Description=SkyNerd Assistant - Local AI personal assistant
After=network.target

[Service]
Type=simple
ExecStart={sys.executable} -m skynerd_assistant daemon start -f
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
'''

    # Save service file
    service_path = Path.home() / ".config" / "systemd" / "user" / "skynerd-assistant.service"
    service_path.parent.mkdir(parents=True, exist_ok=True)
    service_path.write_text(service_content)

    console.print(f"Created service: {service_path}")

    # Enable and start the service
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "skynerd-assistant"], check=True)
        subprocess.run(["systemctl", "--user", "start", "skynerd-assistant"], check=True)
        console.print("[green]✓[/green] Service enabled and started")
    except subprocess.CalledProcessError:
        console.print("[yellow]Note:[/yellow] Run these commands manually:")
        console.print("  systemctl --user daemon-reload")
        console.print("  systemctl --user enable skynerd-assistant")
        console.print("  systemctl --user start skynerd-assistant")


# ============================================================================
# Init Command
# ============================================================================

@app.command()
def init():
    """
    Initialize configuration file.

    Creates ~/.skynerd/config.yaml with default values.
    """
    config_dir = Path.home() / ".skynerd"
    config_file = config_dir / "config.yaml"

    if config_file.exists():
        overwrite = typer.confirm(f"Config already exists at {config_file}. Overwrite?")
        if not overwrite:
            raise typer.Exit(0)

    config_dir.mkdir(parents=True, exist_ok=True)

    default_config = '''# SkyNerd Assistant Configuration

api:
  base_url: https://skynerd-control-production.up.railway.app
  api_key: wu8s57Em.xIA7sVL6do32wcYdEKsMITsl7tD7WjH4

ollama:
  enabled: true
  base_url: http://localhost:11434
  model: gemma3:12b

monitors:
  email_interval_minutes: 1
  task_interval_minutes: 1
  calendar_interval_minutes: 1
  voice_interval_minutes: 1
  reminder_interval_minutes: 1

notifications:
  desktop: true
  slack: true
  sound: true

voice:
  enabled: true
  tts_engine: pyttsx3  # or 'sapi' for Windows, 'polly' for AWS
  voice_rate: 150
  voice_volume: 0.8

debug: false
'''

    config_file.write_text(default_config, encoding="utf-8")
    console.print(f"[green]✓[/green] Created config file: {config_file}")
    console.print()
    console.print("Next steps:")
    console.print(f"  1. Edit {config_file} and set your API key")
    console.print("  2. Run 'skynerd-assistant status' to test the connection")
    console.print("  3. Run 'skynerd-assistant install' to set up auto-start")


# ============================================================================
# Entry Point
# ============================================================================

def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
