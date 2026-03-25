"""Allow running as `python -m src bot --inspect`, `python -m src analyze`, etc."""
import sys

if len(sys.argv) < 2:
    print("Usage: python -m src <command> [options]")
    print("Commands: bot, analyze")
    sys.exit(1)

command = sys.argv.pop(1)  # remove subcommand so argparse sees only flags

if command == "bot":
    from src.bot import main
    main()
elif command == "analyze":
    from src.analyze import main
    main()
else:
    print(f"Unknown command: {command}")
    sys.exit(1)
