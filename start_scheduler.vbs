Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Projects\automation\telegram-bot-project"
WshShell.Run "C:\Projects\automation\telegram-bot-project\venv\Scripts\python.exe -u weather_scheduler.py --now", 0, False
