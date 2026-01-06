#!/usr/bin/env python3
# Description: Send desktop and ntfy.sh notifications on stop
# Deps: requests

import json
import os
import subprocess
import sys
from pathlib import Path


def load_config():
    """Load captain-hook config for notification settings."""
    config_path = Path.home() / ".config" / "captain-hook" / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}


def send_desktop_notification(title: str, message: str):
    """Send a desktop notification."""
    system = sys.platform

    if system == "darwin":
        # macOS
        script = f'display notification "{message}" with title "{title}"'
        subprocess.run(["osascript", "-e", script], capture_output=True)
    elif system == "linux":
        # Linux with notify-send
        subprocess.run(["notify-send", title, message], capture_output=True)
    elif system == "win32":
        # Windows with PowerShell
        ps_script = f"""
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        $template = [Windows.UI.Notifications.ToastTemplateType]::ToastText02
        $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($template)
        $xml.GetElementsByTagName('text')[0].AppendChild($xml.CreateTextNode('{title}'))
        $xml.GetElementsByTagName('text')[1].AppendChild($xml.CreateTextNode('{message}'))
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Claude Code').Show($toast)
        """
        subprocess.run(["powershell", "-Command", ps_script], capture_output=True)


def send_ntfy_notification(server: str, topic: str, title: str, message: str):
    """Send notification via ntfy.sh."""
    try:
        import requests
        requests.post(
            f"{server}/{topic}",
            data=message,
            headers={"Title": title},
            timeout=5,
        )
    except Exception:
        pass  # Silent fail for ntfy


def main():
    data = json.load(sys.stdin)
    config = load_config()
    notify_config = config.get("notify", {})

    # Get stop reason
    stop_reason = data.get("stop_reason", "unknown")

    # Build notification
    title = "Claude Code"
    if stop_reason == "end_turn":
        message = "Task completed"
    elif stop_reason == "user_interrupt":
        message = "Interrupted by user"
    else:
        message = f"Stopped: {stop_reason}"

    # Desktop notification
    if notify_config.get("desktop", True):
        send_desktop_notification(title, message)

    # ntfy.sh notification
    ntfy = notify_config.get("ntfy", {})
    if ntfy.get("enabled") and ntfy.get("topic"):
        send_ntfy_notification(
            ntfy.get("server", "https://ntfy.sh"),
            ntfy["topic"],
            title,
            message,
        )


if __name__ == "__main__":
    main()
