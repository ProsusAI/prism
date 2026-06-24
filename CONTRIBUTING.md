# Contributing to Prism

Thanks for your interest in contributing! Prism is a knowledge layer for Claude Code and Cursor, and we welcome bug reports, feature ideas, and pull requests.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.

## Reporting bugs

Open an issue using the **Bug report** template. Please include:

- What you expected to happen vs. what actually happened
- Steps to reproduce (a minimal example is ideal)
- Your OS, shell, Python version (`python3 --version`), and IDE (Claude Code / Cursor)
- Relevant output from `prism status` and any error messages (scrub secrets first)

Do **not** file security vulnerabilities as public issues — see [SECURITY.md](SECURITY.md).

## Suggesting features

Open an issue using the **Feature request** template. Describe the problem you're trying to solve, not just the solution you have in mind.

## Development setup

Prism is **Python 3.12+ standard library only** — there are no runtime dependencies to install.

```bash
git clone https://github.com/ProsusAI/prism.git
cd prism
./install.sh                       # installs into ~/.prism
python3 -m unittest discover -s tests -p "test_*.py"
```

## Pull requests

1. Fork the repo and create a branch from `main` (`fix/...` or `feat/...`).
2. Keep changes focused — one logical change per PR.
3. Make sure the test suite passes: `python3 -m unittest discover -s tests -p "test_*.py"`.
4. Add tests for new behavior where practical.
5. Fill out the PR template and link any related issue.

### Architectural constraints (please read)

Prism has deliberate, hard constraints. PRs that violate these will be asked to change:

- **Hooks never block the IDE.** `capture.sh` / `capture_cursor.sh` must always exit 0 and only spawn background work.
- **Standard library only** for the Python CLI/library. No third-party Python packages, no ORM, no PyYAML (frontmatter is hand-parsed), no Anthropic/Cursor SDKs.
- **AI calls go through IDE CLIs only** (`claude --print` / `agent -p`) via `lib/agent_runner.py`. No API keys, no SDKs.
- **Storage split** — observations + sessions in SQLite (`~/.prism/prism.db`); engrams stay flat Markdown + YAML frontmatter; the engram index stays `index.json`.
- **MCP stdout is protocol-only.** All logging goes to stderr; a stray `print()` in `lib/` corrupts the JSON-RPC stream.
- **Never read `.env` files.** Config comes from `os.environ` and `config.json` only.
- **Use `subprocess.run(..., capture_output=True, text=True, timeout=N)`**, never `os.system()`.

See [CLAUDE.md](CLAUDE.md) and [DOCS.md](DOCS.md) for the full design rationale.

## Code style

- Match the style of the surrounding code.
- Python: keep `capture.py` fast (it runs on every tool call) and within stdlib + `lib` internals.
- Bash: POSIX-compatible, avoid Bash 4+ features (macOS ships Bash 3.2).

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE), the same license that covers this project.
