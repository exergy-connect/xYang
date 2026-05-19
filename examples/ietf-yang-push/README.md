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
  --anydata-module examples/ietf-yang-push/modules/ietf-distributed-notif@2024-04-21.yang \
  --anydata-module examples/ietf-yang-push/modules/ietf-yp-observation@2025-02-24.yang \
  --anydata-module examples/ietf-yang-push/modules/ietf-alarms@2019-09-11.yang \
  --anydata-module examples/ietf-yang-push/modules/ietf-alarms-x733@2019-09-11.yang
```

- **Host module** — `ietf-yp-notification` defines the `envelope` structure
  (`event-time`, `hostname`, `sequence-number`, `contents` anydata).
- **`--anydata-validation complete`** — checks RFC 7951 qualified members under
  `contents` (here `ietf-yang-push:push-change-update` and augmenting leaves).
- **`--anydata-module`** — loads only the modules needed for that subtree
  (imports resolved via `--include-path`):
  - `ietf-yang-push` — `push-change-update` and `datastore-changes`
  - `ietf-distributed-notif` — `ietf-distributed-notif:message-publisher-id`
  - `ietf-yp-observation` — `ietf-yp-observation:timestamp`,
    `ietf-yp-observation:point-in-time`
  - `ietf-alarms` — `alarm-notification` in the nested `yang-patch` `edit` `value`
  - `ietf-alarms-x733` — `ietf-alarms-x733:*` leaves on that notification

  Omit `--anydata-module` to load every `*.yang` under `--include-path` (slower;
  many vendor modules are not required for this file).

Use `candidate` instead of `complete` for structural checks only (no `must` /
`when` / type constraints on the anydata subtree). See
[`examples/anydata_validation_usage.py`](../anydata_validation_usage.py).

### Nested patch payload

The sample `yang-patch` `edit` `value` carries an `ietf-alarms:alarm-notification`
document. Standard modules `ietf-alarms` and `ietf-alarms-x733` are under
`modules/` and are included in the command above.

The payload also uses vendor prefixes not shipped in this bundle
(`huawei-alarm-type-an`, `an-alarm-management`, `hw-alarm-type-an`). Add those
`.yang` files under `modules/` and pass extra `--anydata-module` paths to validate
those leaves.

`ietf-alarms` also defines `action` and `notification` under list `alarm` (YANG
1.1). xYang parses `notification` there; `action` is still skipped with a warning.

### Parser scope

Many modules under `modules/` use constructs xYang still skips or does not fully
model (see [FEATURES.md](../../FEATURES.md)). If `validate` fails while loading
YANG, narrow `--anydata-module` or trim the import closure.
