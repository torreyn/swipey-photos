# ImageSwiper documentation

Start here if you want the *why* before the *how*. The README covers installing
and using the app; this folder covers design, configuration and hacking.

| Document | Read it when… | Audience |
| --- | --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | you want the toolkit rationale, layer rules, component contracts, threading model, invariants or milestone exit criteria | contributors, reviewers |
| [CONFIGURATION.md](CONFIGURATION.md) | you need every config key, its default, range and failure behaviour | users, packagers |
| [DEVELOPMENT.md](DEVELOPMENT.md) | you are setting up a checkout, running tests, debugging Qt, building the binary or preparing a release | contributors |
| [PACKAGING.md](PACKAGING.md) | you are packaging ImageSwiper, installing the desktop entry, building a binary or AppImage, or preparing a tagged release | packagers, maintainers |
| [assets/](assets/) | you are replacing the placeholder mock-ups | contributors |
| [../screenshots/](../screenshots/) | you are capturing real screenshots (offscreen recipe, sizes, naming) | contributors |
| [../CHANGELOG.md](../CHANGELOG.md) | you want the version history in Keep a Changelog form | users, packagers |
| [../SECURITY.md](../SECURITY.md) | you found a filesystem or data-loss bug and need the private reporting channel | users, researchers |

Suggested reading order for a new contributor:

1. [README → Features](../README.md#features) — what the app does.
2. [ARCHITECTURE §3–§5](ARCHITECTURE.md#3-design-principles) — the rules and the
   contracts you must not break.
3. [DEVELOPMENT §2–§4](DEVELOPMENT.md#2-first-run-setup) — get it running, get
   tests green.
4. [CONTRIBUTING](../CONTRIBUTING.md) — branch names, commit style, definition of
   done.

## Documentation rules

- One source of truth per fact. Configuration keys live in
  `CONFIGURATION.md`; invariants and contracts live in `ARCHITECTURE.md`.
- Relative links only, so the docs render on GitHub, in a local editor and in
  the sdist.
- Code fences carry a language tag; tables carry a header row.
- When a documented behaviour changes, the doc changes in the same pull
  request — a stale doc is a bug.
- Planned behaviour is marked with the milestone that delivers it
  (`planned, M3`) so readers can tell it apart from what the code does today.
