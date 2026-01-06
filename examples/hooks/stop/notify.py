#!/usr/bin/env python3
# Description: Send desktop and ntfy.sh notifications on stop
# Deps: requests
# Env: DESKTOP=true
# Env: NTFY_ENABLED=false
# Env: NTFY_SERVER=https://ntfy.sh
# Env: NTFY_TOPIC=

import json
import os
import subprocess
import sys


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


def get_bool_env(name: str, default: bool = False) -> bool:
    """Get a boolean from env var."""
    val = os.environ.get(name, "").lower()
    if val in ("true", "1", "yes"):
        return True
    if val in ("false", "0", "no"):
        return False
    return default


def main():
    data = json.load(sys.stdin)

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

    # Desktop notification (env var set by captain-hook runner)
    if get_bool_env("NOTIFY_DESKTOP", True):
        send_desktop_notification(title, message)

    # ntfy.sh notification
    ntfy_enabled = get_bool_env("NOTIFY_NTFY_ENABLED", False)
    ntfy_topic = os.environ.get("NOTIFY_NTFY_TOPIC", "")
    if ntfy_enabled and ntfy_topic:
        ntfy_server = os.environ.get("NOTIFY_NTFY_SERVER", "https://ntfy.sh")
        send_ntfy_notification(ntfy_server, ntfy_topic, title, message)


if __name__ == "__main__":
    main()
