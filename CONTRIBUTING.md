# Contributing

Thank you for helping. Issues and pull requests are welcome.

## Issues

- **Bug reports** — what you sent to Claude, what you expected, and the message Claude or the script printed
- **Ideas** — what you want to make and what is missing today
- Questions about the setup are welcome too; the guide is [docs/はじめに.md](docs/はじめに.md)

## Never post

Issues and pull requests are public. Never post:

- recordings, rendered videos or still images of real people
- Google Drive share links or any other private links
- real people's names, companies or titles from a recording
- tokens, passwords or anything else secret

Replace them with placeholders (話者A, `<share link>`) before posting.

## Pull requests

1. Keep the change small and say why it is needed
2. Run the tests and make sure they pass:

   ```bash
   bash scripts/setup.sh
   make test
   ```

3. Do not restyle `studio/telops.py`; new content belongs in an EDL (start from `templates/edl_template.py`)

Engineering details: [docs/engineering.md](docs/engineering.md). Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).
