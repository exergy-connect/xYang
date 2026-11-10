# Agent notes

## Native JSON format

Treat `.yang` as the source and the native JSON as its reversible, canonical form. Never hand-edit one without the other being reproducible. Prefer the native JSON for fast, unambiguous processing. Any lossy or non-reversible change in the transform is a bug: raise a loud error and do not silently drop it.
