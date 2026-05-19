# IETF YANG-Push example

Captured notification payload (`27-push-update.json`) from a device using the
[RFC 8791](https://www.rfc-editor.org/rfc/rfc8791) notification envelope
(`ietf-yp-notification:envelope`) and a `ietf-yang-push:push-change-update`
notification in `contents`.

`modules/` holds the YANG library from the publisher (`yang-lib.xml`).
`subscriptions-info.json` is sample subscription configuration.

## Validate `27-push-update.json`

From the repository root, install xYang (or use `PYTHONPATH=src`):

```bash
pip install -e .
# or: PYTHONPATH=src python3 -m xyang …
```

Validate the envelope and the push notification under `contents` with
anydata subtree validation:

```bash
xyang validate \
  examples/ietf-yang-push/modules/ietf-yp-notification@2025-06-04.yang \
  examples/ietf-yang-push/27-push-update.json \
  --include-path examples/ietf-yang-push/modules \
  --anydata-validation complete \
  --anydata-module examples/ietf-yang-push/modules/ietf-yang-push@2019-09-09.yang \
  --anydata-module examples/ietf-yang-push/modules/ietf-distributed-notif@2024-04-21.yang
```

- **Host module** — `ietf-yp-notification` defines the `envelope` structure
  (`event-time`, `hostname`, `sequence-number`, `contents` anydata).
- **`--anydata-validation complete`** — checks RFC 7951 qualified members under
  `contents` (here `ietf-yang-push:push-change-update` and augmenting leaves).
- **`--anydata-module`** — loads only the modules needed for that subtree;
  omit these flags to load every `*.yang` under `--include-path` (slower, and
  many vendor modules are not required for this file).

Use `candidate` instead of `complete` for structural checks only (no `must` /
`when` / type constraints on the anydata subtree). See
[`examples/anydata_validation_usage.py`](../anydata_validation_usage.py).

### Nested patch payload

The sample `yang-patch` `edit` `value` carries an `ietf-alarms:alarm-notification`
document. Those alarm modules are not in `modules/`; add their `.yang` files with
extra `--anydata-module` paths if you want that subtree validated too.

### Parser scope

Many modules under `modules/` use constructs xYang still skips or does not fully
model (see [FEATURES.md](../../FEATURES.md)). If `validate` fails while loading
YANG, narrow `--anydata-module` or trim the import closure.
