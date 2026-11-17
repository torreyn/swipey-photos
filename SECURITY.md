# Security policy

## Supported versions

ImageSwiper is a desktop tool that moves files inside folders you choose, so
the interesting failure modes are filesystem ones rather than remote ones.

| Version | Supported |
| --- | --- |
| 1.0.x | ✅ |
| < 1.0 | ❌ (never released) |

## Reporting a vulnerability

**Do not open a public issue.** Use GitHub's private reporting: *Security* tab →
*Report a vulnerability*
(<https://github.com/torreyn/image-swiper/security/advisories/new>).

Please include:

- the version (`image-swiper --version`),
- what an attacker could achieve (overwrite a file outside the chosen folder,
  follow a symlink out of the library, execute something via a crafted image
  name, …),
- a minimal reproduction — a shell snippet or a small pytest case is ideal,
- whether the standalone binary or a `pip` install was used.

You can expect an acknowledgement within a week. This is a volunteer project, so
there is no bug-bounty programme; credit in the release notes is offered if you
want it.

## Scope

In scope:

- Files moved or written outside the selected folder, or an existing file
  overwritten instead of suffixed.
- Symlink, traversal or race conditions (`TOCTOU`) in scanning or moving.
- Unsafe handling of image files (Pillow decoding paths that a crafted file can
  abuse).
- Config or log files written world-readable, or leaking paths to other users.

Out of scope:

- Anything that requires an attacker to already control your user account.
- Crashes caused by deliberately corrupted files with no data-loss impact (send a
  normal bug report: unreadable images are meant to be skipped).
- Qt or PyQt6 issues themselves — report those upstream, and tell us if a
  workaround is needed.

## What the app already guarantees

These are tested, so a regression is a security bug:

- Moves are collision-safe: an existing name gains a `_1` suffix, it is never
  overwritten (`utils/file_ops.py`, `core/folder_manager.py`).
- Nothing is ever deleted; rejected images are moved to a folder.
- The config file is replaced atomically with mode `0600`
  (`utils/config.py`).
- Logs redact nothing but stay inside `${XDG_DATA_HOME}/image-swiper/logs/`, so
  check them before pasting one into an issue.
