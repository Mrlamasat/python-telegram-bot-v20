"""Compatibility entrypoint for deployments that run `python /app/bot.py`."""

if __name__ == "__main__":
    import main  # noqa: F401  (imports and runs the bot via main.py)
