# Contributing to Nexus

We would love your help to make Nexus Framework better! 

## Philosophy

1. **Zero unnecessary dependencies.** Using the standard library where applicable makes the base installation lightweight and fast. External dependencies (like `pydantic`, `httpx`, or AI client SDKs) should be restricted to `extras`.
2. **Developer Experience.** Error messages should be helpful, APIs should be obvious.
3. **Async-First.** All I/O operations (Database, AI requests, network requests) must be asynchronous and non-blocking.

## Development Setup

1. Fork the repository and clone it locally.
2. Initialize a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install development dependencies:
   ```bash
   pip install -e ".[dev,full]"
   ```

## Workflow

1. Create a descriptive branch (`feature/caching-redis`, `bugfix/auth-header`).
2. Write tests for any new functionality or bug fixes inside `tests/`.
3. Ensure the test suite passes:
   ```bash
   pytest tests/
   python run_tests.py
   ```
4. Run the Linter:
   ```bash
   ruff check nexus/
   ```
5. Commit and open a Pull Request! Keep your commit messages clear, e.g. `feat(core): implement FastRAG integration` or `fix(orm): proper timezone handling on auto_now`.

## Submitting Pull Requests

Please make sure to link any related issues to your PR, and briefly explain the changes inside the PR description body. A maintainer will review your code shortly!
