# Test consolidation (#154)

[#154](https://github.com/exergy-connect/xYang/issues/154) asked for at most 400 distinct
logical test cases. **That target is not met.** The suite went from 1,649 to 1,495 logical
cases. The 627 shared conformance instances alone are more than 400. The reasons are under
[Remaining blockers](#remaining-blockers).

## Method

- **Before:** `main` at `da3775c` (after #155 merged). The work started from `fba7482`; #155 was
  merged in with a normal merge, so `da3775c` is the comparable base.
- **Counting:** [`tests/inventory.py`](../tests/inventory.py), run on both trees. It reads
  `pytest --collect-only`, `vitest list --json` and `tests/cases/**/case.json`. A shared instance
  counts once. Every other collected item counts once for its runtime. A loop inside one test
  function is one item; the count cannot see inside it, so it is a lower bound on scenarios.
  Migrating such a loop to shared instances makes each scenario visible, which can raise the
  count.
- **Timing:** same VM, Python 3.12.3, Node 24.22.3, two runs each, back to back. The `main`
  worktree had no `ts/dist`, so its browser-bundle smoke test was skipped there.

## Counts

| | `da3775c` (main) | this branch |
|---|---:|---:|
| Logical cases | 1,649 | 1,495 |
| shared instances (`tests/cases`) | 510 | 627 |
| Python only | 632 | 496 |
| TypeScript only | 507 | 372 |
| Python collected items | 1,142 | 1,123 |
| `pytest -q` | 1,137 passed, 3 skipped, 2 xfailed | 1,118 passed, 3 skipped, 2 xfailed |
| TypeScript tests (`vitest list` / `vitest run`) | 1,017 / 1,017 passed, 2 skipped | 999 / 999 passed, 1 skipped |
| Python test files / TypeScript test files with items | 97 / 98 | 85 / 84 |
| Mirrored Python + TypeScript items (files with the same stem) | 459 + 425 | 334 + 304 |
| CI test executions per PR (5 Python × items + 2 Node × items + 2 conformance jobs × shared) | 8,764 | 8,867 |

At `fba7482` (before #155) the same script gave 1,495 logical cases (438 shared, 590 Python,
467 TypeScript), 1,028 Python items, 905 TypeScript items.

The number of executions per PR went up by about 1%. Each instance moved into `tests/cases` runs in
every Python matrix job, in both Node jobs, and again in the two conformance jobs. The
conformance workflow has no path filter, so it is the only check that runs the cases on every
PR. It was left alone.

**Expected failures and skips.** The two Python xfails did not change
(`encoding/dict-style:native int64 above 2^53` and `parser/substatements/container-grouping-hidden`).
TypeScript has none. The three Python skips are the same (Huawei directory unset, `pyang` and
`owlrl` not installed). The one TypeScript skip is the Huawei suite. No skip or xfail was added.

## Timings

| Command | `da3775c` | this branch |
|---|---:|---:|
| `pytest --collect-only -q` | 0.49 / 0.51 s | 0.49 / 0.49 s |
| `pytest -q -W error::DeprecationWarning` | 38.6 / 39.0 s | 33.9 / 34.5 s |
| `pytest tests/test_cases.py -q` | 1.11 / 1.13 s | 1.24 / 1.25 s |
| `npx vitest run` | 8.66 / 8.76 s | 7.25 / 7.65 s |
| `npx vitest run test/cases.test.ts` | 1.31 / 1.38 s | 1.35 / 1.37 s |

`tests/test_ontology_hypergraph.py` takes about 25 s of the Python run. Parsing its model takes
14 ms; validating one projected graph takes about 0.19 s, and almost every test validates one.
Speeding that up is a validator change, which is out of scope here.

## Ontology tests run on release

The 400-case target is still not met. The logical count is unchanged at 1,495, and the 93
ontology tests stay inside it.

Pull requests and pushes no longer run them. `tests.yml` passes `-m "not ontology"` (69 Python
items deselected, not skipped). `npm test` excludes `test/ontology_audit_example.test.ts` (24
TypeScript tests). Nothing else is deselected: the same command still runs the other 1,051
passing Python tests, the Huawei skip, and the two xfails.

| | consolidation head, before this split | pull-request CI after it |
|---|---:|---:|
| Logical cases | 1,495 | 1,495 |
| CI executions per PR | 8,867 | 8,474 |
| `pytest -q -m "not ontology" -W error::DeprecationWarning` | (not used; full `pytest -q` was 33.9 / 34.5 s) | 9.75 / 9.40 s: 1051 passed, 1 skipped, 69 deselected, 2 xfailed |
| `npm test` | 999 passed, 1 skipped, about 7.5 s | 975 passed, 1 skipped, 7.33 s |

A published release (`release: published`, the event used by the PyPI, npm, artifact, QuickJS,
and benchmark workflows) runs the 93 ontology tests once: 69 Python and 24 TypeScript.
`workflow_dispatch` runs the same jobs and publishes nothing. With the optional tools installed,
the Python file was 69 passed and 0 skipped in 29.1 s. `npm run test:ontology` was 24 passed in
1.0 s. The release job fails if the Python run skips anything, so a missing pyang or OWL RL
install does not pass. Those two checks no longer show up as skips in pull-request pytest,
because the whole file is deselected there.

## What changed

- **Mirrored tests moved into shared cases.** When a Python test and its TypeScript twin only
  parsed YANG, validated an instance and checked the result, the scenario became a shared
  instance and both tests were deleted. That happened only when both runtimes agree on the exact
  `(path, code)` set without a new xfail. 47 case directories were added and 6 extended.
- **Duplicates deleted.** A test was deleted when a retained check asserts the same behavior:
  same construct, same input class, same outcome and the same code, path or message when the old
  test checked them. The table below names each retained check.
- **Equivalence classes.** `contains`, `starts-with` and `substring-after` lost their
  zero-argument instance. All three use the same `_require_arity(ast, 2)` check, and their
  one-argument instance still covers too few arguments. `substring-before` keeps the zero-argument
  instance as the empty-argument-list boundary.
- **Setup.** Models and JSON Schemas are parsed once per file (module-scoped fixtures,
  `beforeAll`). Ontology publications are loaded once and deep-copied per test. Registry-parity
  Node dumps are cached. The per-command `--help` and malformed-invocation loops run in-process.
  Real subprocesses still cover the top-level `--help`/`-h`, bare `xyang`, one subcommand's
  `--help`, an unknown command and an unknown global flag.
- **Kept on purpose:** runtime API contracts (non-mutation, legacy `validate()` strings, cache
  statistics), parser/AST and JSON Schema round-trips, every CLI contract, issue-linked
  regressions, all example fixtures, and the tests #155 added.

Four removals made by the first pass were reverted after review, because they lost coverage:

| Removal | Why it was restored |
|---|---|
| `tests/json/test_typedef.py`, `test_change_history_policy.py` and their TypeScript twins: validation through the `.yang.json`-loaded model | The replacement shared cases only load `.yang`. The native JSON form must enforce the same constraints. |
| `test_ontology_hypergraph.py::test_invalid_graphs_fail_loudly[… "one assessor"]` (reviewer role) | Zero assessors is the lower boundary of "exactly one". Appending a second assessor only tests the upper one. |
| `test_release_benchmark.py::test_schema_rejects_broken_results[warmup_per_process=5]` | The rule is `operations_per_process != 1 or warmup_per_process != 0`; each operand needs a case. |
| Four `tests/test_if_feature.py` tests folded into two | That bundled distinct scenarios to lower the count. |

## Remaining blockers

1. **Shared instances: 627.** Each one is a separate instance document with its own expected
   error set. Most are deliberate boundaries: argument count, empty strings, encoding modes,
   rpc/action wrapper variants, key and prefix forms. Merging them would hide scenarios, and
   deleting them would drop boundaries. This floor is above 400 before any runtime-specific test.
2. **Mirrored runtime-specific tests: 334 Python + 304 TypeScript.** They check AST shape,
   JSON Schema output, API objects and CLI streams, which `case.json` cannot express. Counting
   each scenario once would need a second shared fixture format for parser and API outputs. That
   is a framework change, outside this issue's bounded scope. It would remove about 300 logical
   cases at most.
3. **Examples and tooling: 92 ontology example tests (68 Python, 24 TypeScript), 25 benchmark
   tooling tests, 12 skill-document tests.** Each guards a separate model constraint, documented
   fixture or script contract.
4. **#155's new tests** were merged and not consolidated, as requested while that work landed:
   49 prefixed-XPath-step tests (25 Python, 24 TypeScript), 32 new rpc/action tests, and most of
   the 72 shared instances added between `fba7482` and `da3775c`. The only change is the
   usage-error table that #155 reworded: it was already replaced by shared `usage_error`
   instances on this branch (see the merge table below).

## Traceability

Each row is a removed or migrated check and the retained check that covers it. Case ids are
`tests/cases/<area>/<case>:<instance name>`.

### Shared-case arity trim

| removed check | action | retained coverage | note |
|---|---|---|---|
| `tests/cases/xpath/contains:missing args` | deleted | `tests/cases/xpath/contains:one arg` + `tests/cases/xpath/substring-before:missing args` | same `_require_arity(ast, 2)`; empty argument list kept once |
| `tests/cases/xpath/starts-with:missing args` | deleted | `tests/cases/xpath/starts-with:one arg` + `tests/cases/xpath/substring-before:missing args` | same |
| `tests/cases/xpath/substring-after:missing args` | deleted | `tests/cases/xpath/substring-after:one arg` + `tests/cases/xpath/substring-before:missing args` | same |

### Merge with #155

| removed check | action | retained coverage | note |
|---|---|---|---|
| `tests/test_unsupported_skip.py::test_module_rejects_top_level_input_output[input/output]`, `test_container_rejects_rpc` and the TypeScript twins | migrated | `tests/cases/parser/arguments/top-level-input`, `top-level-output`, `tests/cases/parser/substatements/container-rpc` | schema_error with the same message in both runtimes |
| `tests/test_rpc_validation.py::test_usage_errors_raise_value_error[*]` and the TypeScript `rejects options` table (#155 wording) | migrated | `tests/cases/operations/rpc-must:unknown rpc`, `direction without rpc`, `context without rpc`, `invalid direction`, `empty rpc name`; `tests/cases/operations/rpc-context:context is not an object` | `usage_error` substrings |

### XPath, must, leafref paths

| removed check | action | retained coverage | note |
|---|---|---|---|
| `tests/test_leaf_must_relative_path.py::test_leaf_must_relative_path_valid` | migrated | `tests/cases/xpath/leaf-must-relative:flag set` | |
| `tests/test_leaf_must_relative_path.py::test_leaf_must_relative_path_invalid` | migrated | `tests/cases/xpath/leaf-must-relative:flag unset` | |
| `ts/test/leaf_must_relative_path.test.ts::accepts ref_rel when top/flag = 1` | migrated | `tests/cases/xpath/leaf-must-relative:flag set` | |
| `ts/test/leaf_must_relative_path.test.ts::rejects ref_rel when top/flag = 0` | migrated | `tests/cases/xpath/leaf-must-relative:flag unset` | |
| `tests/test_leaf_list_current.py::test_leaf_list_current_single_constraint` | migrated | `tests/cases/conditions/leaf-list-must:all elements satisfied` + `negative element` + `zero element` | multi-doc test → instances |
| `tests/test_leaf_list_current.py::test_leaf_list_current_multiple_constraints` | merged | `tests/cases/conditions/leaf-list-must:all elements satisfied` + `above max` + `negative element` | same leaf-list current() class; bounds kept |
| `tests/test_leaf_list_current.py::test_leaf_list_current_with_relative_paths` | migrated | `tests/cases/conditions/leaf-list-must:all elements satisfied` + `below min_value` | |
| `tests/test_leaf_list_current.py::test_leaf_list_current_empty_list` | migrated | `tests/cases/conditions/leaf-list-must:empty leaf-list` | |
| `tests/test_leaf_list_current.py::test_leaf_list_current_single_value` | migrated | `tests/cases/conditions/leaf-list-must:single element ok` + `single element bad` | |
| `tests/test_leaf_list_current.py::test_leaf_list_current_vs_leaf_comparison` | migrated | `tests/cases/conditions/leaf-list-must:leaf ok leaf-list bad` | |
| `ts/test/leaf_list_current.test.ts::current() is bound to each leaf-list value` | migrated | `tests/cases/conditions/leaf-list-must` (same instances as Python) | |
| `ts/test/leaf_list_current.test.ts::multiple must constraints with current()` | merged | `tests/cases/conditions/leaf-list-must` | |
| `ts/test/leaf_list_current.test.ts::current() with relative path to sibling leaf` | migrated | `tests/cases/conditions/leaf-list-must` | |
| `ts/test/leaf_list_current.test.ts::empty leaf-list skips must` | migrated | `tests/cases/conditions/leaf-list-must:empty leaf-list` | |
| `ts/test/leaf_list_current.test.ts::single element leaf-list` | migrated | `tests/cases/conditions/leaf-list-must:single element ok/bad` | |
| `ts/test/leaf_list_current.test.ts::leaf-list current() vs leaf` | migrated | `tests/cases/conditions/leaf-list-must:leaf ok leaf-list bad` | |
| `tests/test_must_resolver_minimal.py::test_primary_key_fields_name_equals_current` | migrated | `tests/cases/xpath/must-sibling-current:matching field` | |
| `tests/test_must_resolver_minimal.py::test_primary_key_fields_name_equals_current_invalid` | migrated | `tests/cases/xpath/must-sibling-current:missing field` | |
| `tests/test_must_resolver_minimal.py::test_must_string_length_fails_empty` | deleted | `tests/cases/xpath/functions:string-length()` | same string-length must outcome |
| `tests/test_must_resolver_minimal.py::test_must_absolute_or_relative_list_item` | migrated | `tests/cases/xpath/must-or-absolute` (consolidated false / type test / all clauses false) | schema aligned to TS mirror (real `consolidated` leaf) |
| `tests/test_must_resolver_minimal.py::test_must_boolean_current_equals_true` | deleted | `tests/cases/xpath/functions:boolean()` + `true()` + `current()` | `boolean(current())` is true for any present leaf node-set; no value semantics |
| `ts/test/must_resolver_minimal.test.ts::accepts primary_key when matching sibling fields` | migrated | `tests/cases/xpath/must-sibling-current:matching field` | |
| `ts/test/must_resolver_minimal.test.ts::rejects primary_key when no sibling field matches` | migrated | `tests/cases/xpath/must-sibling-current:missing field` | |
| `ts/test/must_resolver_minimal.test.ts::supports string-length(.) must on leaf` | deleted | `tests/cases/xpath/functions:string-length()` | |
| `ts/test/must_resolver_minimal.test.ts::supports absolute path with OR logic` | migrated | `tests/cases/xpath/must-or-absolute` | |
| `tests/test_duplicate_must_bug.py::test_computed_field_ref_valid_minimal` | migrated | `tests/cases/xpath/deep-relative-current:referenced field exists` | also added missing-field negative |
| `ts/test/duplicate_must_bug.test.ts::accepts valid data when must count(...current())` | migrated | `tests/cases/xpath/deep-relative-current:referenced field exists` | |
| `tests/test_deref_standalone.py::test_deref_in_path_expression_valid` | migrated | `tests/cases/xpath/deref-foreign-key:deref path and child_fk ok` | |
| `tests/test_deref_standalone.py::test_deref_in_path_expression_invalid` | migrated | `tests/cases/xpath/deref-foreign-key:missing entity` | expects must+leafref set |
| `tests/test_deref_standalone.py::test_deref_in_predicate_valid` | migrated | `tests/cases/xpath/deref-foreign-key:deref path and child_fk ok` | same schema/outcome class |
| `tests/test_deref_standalone.py::test_deref_in_predicate_invalid` | migrated | `tests/cases/xpath/deref-foreign-key:missing entity` | |
| `tests/test_deref_standalone.py::test_deref_child_fk_foreignKeys_valid` | migrated | `tests/cases/xpath/deref-foreign-key:deref path and child_fk ok` | |
| `tests/test_deref_standalone.py::test_deref_child_fk_foreignKeys_invalid` | migrated | `tests/cases/xpath/deref-foreign-key:child_fk without foreignKeys` | |
| `ts/test/deref_standalone.test.ts::*` (6 tests) | migrated | `tests/cases/xpath/deref-foreign-key` | mirrors above |
| `tests/test_must_on_leafref_list.py::test_must_on_list_with_leafref_valid` | migrated | `tests/cases/xpath/must-leafref-list:ref_name matches` | |
| `tests/test_must_on_leafref_list.py::test_must_on_list_with_leafref_invalid` | migrated | `tests/cases/xpath/must-leafref-list:ref_name mismatched` | |
| `tests/test_must_on_leafref_list.py::test_must_on_list_with_leafref_current_context` | migrated | `tests/cases/xpath/must-leafref-list` | same current()/leafref-list must class |
| `tests/test_must_on_leafref_list.py::test_must_with_string_concatenation_plus_operator` | migrated | `tests/cases/xpath/must-concat` | dropped AST-only asserts; validation retained |
| `tests/test_must_on_leafref_list.py::test_must_with_plus_operator_foreignkeys` | migrated | `tests/cases/xpath/deref-type-match` | |
| `ts/test/must_on_leafref_list.test.ts::must on list with leafref: valid` | migrated | `tests/cases/xpath/must-leafref-list:ref_name matches` | |
| `ts/test/must_on_leafref_list.test.ts::must on list with leafref: invalid` | migrated | `tests/cases/xpath/must-leafref-list:ref_name mismatched` | |
| `ts/test/must_on_leafref_list.test.ts::must on list: current() is list entry` | migrated | `tests/cases/xpath/must-leafref-list` | |
| `ts/test/must_on_leafref_list.test.ts::list must with concat()` | migrated | `tests/cases/xpath/must-concat` | |
| `ts/test/must_on_leafref_list.test.ts::foreignKeys-style must with deref` | migrated | `tests/cases/xpath/deref-type-match` | |
| `tests/test_xpath_value_list.py::test_value_list_equality_true` | migrated | `tests/cases/xpath/value-list:string and number in lists` | |
| `tests/test_xpath_value_list.py::test_value_list_equality_false` | migrated | `tests/cases/xpath/value-list:string not in list` | |
| `tests/test_xpath_value_list.py::test_value_list_numbers` | migrated | `tests/cases/xpath/value-list:string and number in lists` + `number not in list` | |
| `ts/test/xpath_value_list.test.ts::evaluates type = (...) true` | migrated | `tests/cases/xpath/value-list:string and number in lists` | |
| `ts/test/xpath_value_list.test.ts::evaluates type = (...) false` | migrated | `tests/cases/xpath/value-list:string not in list` | |
| `ts/test/xpath_value_list.test.ts::evaluates numeric value list` | migrated | `tests/cases/xpath/value-list` | |
| `tests/test_leafref_relative_path.py::test_leafref_relative_path_invalid_reference` | deleted | `tests/cases/references/leafref:dangling relative` | same relative leafref require-instance miss |
| `ts/test/leafref_relative_path.test.ts::invalid relative-path leafref reference is rejected` | deleted | `tests/cases/references/leafref:dangling relative` | |
| `tests/test_absolute_paths.py::test_absolute_path_entities_list` | deleted | `tests/cases/xpath/must-absolute:absolute flag unset` | absolute must path class; old test soft-skipped on meta-model bug |
| `tests/test_absolute_paths.py::test_absolute_path_with_relative_navigation` | deleted | `tests/cases/xpath/must-absolute:absolute with relative predicate *` | had no assertions |
| `tests/test_absolute_paths.py::test_absolute_path_simple` | deleted | `tests/cases/xpath/must-absolute` | smoke-only |
| `tests/test_absolute_paths.py::test_absolute_path_in_computed_field_validation` | deleted | `tests/cases/xpath/deep-relative-current` | same deep relative `fields[name=current()]` class |
| `tests/test_absolute_paths.py::test_absolute_path_vs_relative_path` | deleted | `tests/cases/xpath/must-sibling-current` | primary_key `../fields[name=current()]` |
| `ts/test/absolute_paths.test.ts::parses meta-model containing absolute-path constraints` | deleted | `tests/cases/xpath/must-absolute` (module load) | parse+validate covered by shared runner |
| `ts/test/absolute_paths.test.ts::parses inline module with absolute path in must` | deleted | `tests/cases/xpath/must-absolute` | |
| `ts/test/absolute_paths.test.ts::parses inline module with absolute path and relative navigation` | deleted | `tests/cases/xpath/must-absolute:absolute with relative predicate *` | |
| `ts/test/absolute_paths.test.ts::validation smoke: list-heavy data` | deleted | `tests/cases/xpath/must-absolute` | |
| `ts/test/absolute_paths.test.ts::validation smoke: absolute/relative mixed` | deleted | `tests/cases/xpath/must-absolute` | |
| `tests/test_xpath_caching.py` validation overlap (not deleted) | — | also covered by `xpath/must-absolute` + `xpath/leaf-must-relative` | kept for cache-stats API asserts (see KEPT) |

### Meta-model example

| removed check | action | retained coverage | note |
|---|---|---|---|
| tests/meta-model/test_must.py::test_entity_field_limit_valid | deleted | tests/meta-model/test_must.py::test_primary_key_reference_valid | Same ≤7 non-array fields must; positive covered by any small valid entity |
| ts/test/meta-model/must.test.ts::entity_field_limit_valid | deleted | ts/test/meta-model/must.test.ts::primary_key_reference_valid | Mirror |
| tests/meta-model/test_must.py::test_entity_name_underscore_valid | deleted | tests/meta-model/test_must.py::test_primary_key_reference_valid | Underscore-within-limit positive covered by name `e` |
| ts/test/meta-model/must.test.ts::entity_name_underscore_valid | deleted | ts/test/meta-model/must.test.ts::primary_key_reference_valid | Mirror |
| tests/meta-model/test_must.py::test_mindate_type_valid | deleted | tests/meta-model/test_new_meta_model_required_default.py::test_min_max_and_minDate_on_field_valid | Same minDate-on-date must |
| ts/test/meta-model/must.test.ts::mindate_type_valid | deleted | ts/test/meta-model/new_meta_model_required_default.test.ts::min_max_and_minDate_on_field_valid | Mirror |
| tests/meta-model/test_must.py::test_mindate_type_invalid | deleted | tests/meta-model/test_new_meta_model_required_default.py::test_minDate_rejected_for_string_primitive | Same minDate-on-non-date must |
| ts/test/meta-model/must.test.ts::mindate_type_invalid | deleted | ts/test/meta-model/new_meta_model_required_default.test.ts::minDate_rejected_for_string_primitive | Mirror |
| tests/meta-model/test_must.py::test_maxdate_type_valid | deleted | tests/meta-model/test_new_meta_model_required_default.py::test_min_max_and_minDate_on_field_valid | maxDate on date covered there |
| ts/test/meta-model/must.test.ts::maxdate_type_valid | deleted | ts/test/meta-model/new_meta_model_required_default.test.ts::min_max_and_minDate_on_field_valid | Mirror |
| tests/meta-model/test_must.py::test_computed_binary_two_fields_valid | deleted | tests/meta-model/test_must.py::test_computed_reference_exists_valid | Same add-with-2-fields positive (latter also sets consolidated) |
| ts/test/meta-model/must.test.ts::computed_binary_two_fields_valid | deleted | ts/test/meta-model/must.test.ts::computed_reference_exists_valid | Mirror |
| tests/meta-model/test_must.py::test_required_no_default_valid | deleted | tests/meta-model/test_new_meta_model_required_default.py::test_required_and_default_valid_when_exclusive | Same required-without-default positive |
| ts/test/meta-model/must.test.ts::required_no_default_valid | deleted | ts/test/meta-model/new_meta_model_required_default.test.ts::required_and_default_valid_when_exclusive | Mirror |
| tests/meta-model/test_must.py::test_required_with_default_invalid | deleted | tests/meta-model/test_new_meta_model_required_default.py::test_required_true_with_default_fails_must | Same required+default must |
| ts/test/meta-model/must.test.ts::required_with_default_invalid | deleted | ts/test/meta-model/new_meta_model_required_default.test.ts::required_true_with_default_fails_must | Mirror |
| tests/meta-model/test_must.py::test_composite_subcomponent_type_valid | deleted | tests/meta-model/test_new_meta_model_required_default.py::test_default_on_composite_subfield_valid | Non-nested composite subfields still validated |
| ts/test/meta-model/must.test.ts::composite_subcomponent_type_valid | deleted | ts/test/meta-model/new_meta_model_required_default.test.ts::default_on_composite_subfield_valid | Mirror |
| tests/meta-model/test_computed_field_cross_entity_foreign_key.py::test_computed_field_cross_entity_foreign_key_valid | deleted | tests/meta-model/test_must.py::test_computed_cross_entity_fk_valid | Dedicated file valid skipped consolidated (weaker); must keeps consolidated=true positive |
| ts/test/meta-model/computed_field_cross_entity_foreign_key.test.ts::computed_field_cross_entity_foreign_key_valid | deleted | ts/test/meta-model/must.test.ts::computed_cross_entity_fk_valid | Mirror; file removed |
| tests/meta-model/test_computed_field_cross_entity_foreign_key.py::test_computed_field_cross_entity_foreign_key_invalid_no_foreign_key | deleted | tests/meta-model/test_must.py::test_computed_cross_entity_no_fk_invalid | Same cross-entity-without-FK must |
| ts/test/meta-model/computed_field_cross_entity_foreign_key.test.ts::computed_field_cross_entity_foreign_key_invalid_no_foreign_key | deleted | ts/test/meta-model/must.test.ts::computed_cross_entity_no_fk_invalid | Mirror; file removed |
| tests/meta-model/test_foreign_key_field_exists.py::test_foreign_key_field_exists_valid | deleted | tests/meta-model/test_must.py::test_foreign_key_type_match_valid | Identical parent/child FK valid shape |
| ts/test/meta-model/foreign_key_field_exists.test.ts::foreign_key_field_exists_valid | deleted | ts/test/meta-model/must.test.ts::foreign_key_type_match_valid | Mirror |
| tests/meta-model/test_composite_primary_key_sample.py::test_composite_primary_key_sample_validates | deleted | tests/meta-model/test_composite_primary_key_sample.py::test_composite_primary_key_points_at_composite_field | Latter already validates then asserts structure |
| ts/test/meta-model/composite_primary_key_sample.test.ts::composite_primary_key_sample_validates | deleted | ts/test/meta-model/composite_primary_key_sample.test.ts::composite_primary_key_points_at_composite_field | Mirror |
| tests/meta-model/test_new_meta_model_sample.py::test_new_meta_model_sample_yaml_validates | deleted | tests/meta-model/test_new_meta_model_sample.py::test_new_meta_model_sample_covers_all_primitive_enums_and_type_shapes | Latter already validates then asserts content |
| ts/test/meta-model/new_meta_model_sample.test.ts::new_meta_model_sample_yaml_validates | deleted | ts/test/meta-model/new_meta_model_sample.test.ts::new_meta_model_sample_covers_all_primitive_enums_and_type_shapes | Mirror |
| tests/meta-model/test_new_meta_model_required_default.py::test_default_on_entity_field_primitive_definition_accepted | merged | tests/meta-model/test_new_meta_model_required_default.py::test_default_on_entity_field_with_type_definition_accepted | Same “default on definition-ref site” class (enum vs primitive); no TS twin |

### Operations, CLI, public API

| removed check | action | retained coverage | note |
|---|---|---|---|
| tests/test_rpc_validation.py::test_old_behavior_without_rpc_is_unknown_field | deleted | tests/cases/operations/rpc-must:no rpc: wrapper is an unknown field | same unknown-field on wrapper |
| tests/test_rpc_validation.py::test_self_link_fails_must_with_the_error_message | deleted | tests/cases/operations/rpc-must:self link | must + error-message |
| tests/test_rpc_validation.py::test_other_target_passes | deleted | tests/cases/operations/rpc-must:valid input / explicit direction input | valid rpc input |
| tests/test_rpc_validation.py::test_native_json_takes_bare_parameters | deleted | tests/cases/operations/rpc-must:self link, native JSON | bare params + must path |
| tests/test_rpc_validation.py::test_output_direction | deleted | tests/cases/operations/rpc-must:valid output + output missing mandatory | output direction |
| tests/test_rpc_validation.py::test_context_joins_the_operation_node | deleted | tests/cases/operations/rpc-context:references resolve in context (+ no context leafrefs) | leafref via context |
| tests/test_rpc_validation.py::test_wrapper_is_not_an_xpath_level | deleted | tests/cases/operations/rpc-must:valid input | `../source` must against operation node |
| tests/test_rpc_validation.py::test_usage_errors_raise_value_error[kwargs0-no rpc 'nope'] | deleted | tests/cases/operations/rpc-must:unknown rpc | usage_error |
| tests/test_rpc_validation.py::test_usage_errors_raise_value_error[kwargs1-direction…] | deleted | tests/cases/operations/rpc-must:direction without rpc | usage_error |
| tests/test_rpc_validation.py::test_usage_errors_raise_value_error[kwargs2-context…] | deleted | tests/cases/operations/rpc-must:context without rpc | usage_error |
| tests/test_rpc_validation.py::test_usage_errors_raise_value_error[kwargs3-direction sideways] | migrated | tests/cases/operations/rpc-must:invalid direction | appended usage_error instance |
| tests/test_rpc_validation.py::test_usage_errors_raise_value_error[kwargs4-context list] | deleted | tests/cases/operations/rpc-context:context is not an object | usage_error |
| tests/test_rpc_validation.py::test_usage_errors_raise_value_error[kwargs5-empty rpc] | migrated | tests/cases/operations/rpc-must:empty rpc name | appended usage_error instance |
| ts/test/rpc-validation.test.ts::without rpc the wrapper is an unknown field | deleted | tests/cases/operations/rpc-must:no rpc: wrapper is an unknown field | mirror |
| ts/test/rpc-validation.test.ts::a self link fails must with the error message | deleted | tests/cases/operations/rpc-must:self link (+ valid input) | TS also asserted other target |
| ts/test/rpc-validation.test.ts::takes bare parameters with nativeJson | deleted | tests/cases/operations/rpc-must:self link, native JSON | mirror |
| ts/test/rpc-validation.test.ts::validates the output | deleted | tests/cases/operations/rpc-must:valid output + output missing mandatory | mirror |
| ts/test/rpc-validation.test.ts::joins the context to the operation node | deleted | tests/cases/operations/rpc-context:references resolve in context | mirror |
| ts/test/rpc-validation.test.ts::rejects options {"rpc":"nope"} | deleted | tests/cases/operations/rpc-must:unknown rpc | mirror |
| ts/test/rpc-validation.test.ts::rejects options {"direction":"output"} | deleted | tests/cases/operations/rpc-must:direction without rpc | mirror |
| ts/test/rpc-validation.test.ts::rejects options {"context":{}} | deleted | tests/cases/operations/rpc-must:context without rpc | mirror |
| ts/test/rpc-validation.test.ts::rejects options {"rpc":"add-link","direction":"sideways"} | migrated | tests/cases/operations/rpc-must:invalid direction | mirror |
| ts/test/rpc-validation.test.ts::rejects options {"rpc":"add-link","context":[]} | deleted | tests/cases/operations/rpc-context:context is not an object | mirror |
| ts/test/rpc-validation.test.ts::rejects options {"rpc":""} | migrated | tests/cases/operations/rpc-must:empty rpc name | mirror |
| tests/test_native_json_cli.py::test_library_default_rejects_native_repro | deleted | tests/cases/encoding/dict-style:rfc rejects native keyed list with empty null + native keyed list with empty null | library encoding |
| ts/test/native-json-cli.test.ts library half of rejects/accepts | deleted | same dict-style instances | CLI half kept |
| tests/test_cli_include_path.py::test_cli_help_lists_include_path[parse] | deleted | tests/test_cli_help.py::test_help_lists_registered_commands_and_options | all command options listed |
| tests/test_cli_include_path.py::test_cli_help_lists_include_path[validate] | deleted | tests/test_cli_help.py::test_help_lists_registered_commands_and_options | same |
| tests/test_cli_include_path.py::test_cli_help_lists_include_path[convert] | deleted | tests/test_cli_help.py::test_help_lists_registered_commands_and_options | same |
| tests/test_coercion.py::test_boolean_coercion_string_true | migrated | tests/cases/xpath/type-coercion:boolean string true equals true() | |
| tests/test_coercion.py::test_boolean_coercion_string_false | migrated | tests/cases/xpath/type-coercion:boolean string false not equal false() | |
| tests/test_coercion.py::test_boolean_coercion_with_boolean_function | migrated | tests/cases/xpath/type-coercion:boolean() of string true / boolean() of non-empty string false | |
| tests/test_coercion.py::test_int32_numeric_string_is_a_type_error | migrated | tests/cases/xpath/type-coercion:int32 numeric string is a type error | |
| tests/test_coercion.py::test_int32_negative_numeric_string_is_a_type_error | migrated | tests/cases/xpath/type-coercion:int32 negative numeric string | |
| tests/test_coercion.py::test_int32_must_constraint_on_json_numbers | migrated | tests/cases/xpath/type-coercion:int32 JSON number satisfies must / fails must | |
| tests/test_coercion.py::test_boolean_already_typed | migrated | tests/cases/xpath/type-coercion:typed boolean true | |
| tests/test_coercion.py::test_int32_already_typed | migrated | tests/cases/xpath/type-coercion:typed int32 | |
| tests/test_coercion.py::test_leaf_list_boolean_coercion | migrated | tests/cases/xpath/type-coercion:leaf-list boolean strings | |
| tests/test_coercion.py::test_leaf_list_int32_numeric_strings_are_type_errors | migrated | tests/cases/xpath/type-coercion:leaf-list int32 numeric strings | |
| tests/test_coercion.py::test_nested_container_boolean_string_and_int32_number | deleted | tests/cases/xpath/type-coercion:boolean string true equals true() + int32 JSON number satisfies must | composition already covered |
| ts/test/coercion.test.ts::(all 11 parity cases) | migrated/deleted | same type-coercion instances (+ nested deleted as composition) | mutation kept separately |
| ts/test/unknown_fields.test.ts::rejects unknown members inside a choice case | migrated | tests/cases/choice/unknown-member:unknown member inside choice case | file deleted |
| ts/test/unknown_fields.test.ts::accepts modeled choice children and opaque payload contents | migrated | tests/cases/choice/unknown-member:modeled choice children and opaque payloads | |
| ts/test/unknown_fields.test.ts::does not treat a choice or case name as an instance member | migrated | tests/cases/choice/unknown-member:choice and case names are not members | |
| ts/test/api-smoke.test.ts::parses a basic module from string | deleted | ts/test/parse_entry_points.test.ts + many parse tests | weak smoke |
| ts/test/api-smoke.test.ts::validates example data | deleted | tests/test_validate_api.py / shared structure cases | only asserted typeof boolean |
| ts/test/api-smoke.test.ts::resolves qualified top level via encoding helper | deleted | ts/test/rfc7951_resolve.test.ts::resolveQualifiedTopLevel finds statement… | duplicate |
| tests/test_single_parse.py::test_yang_expressions_parsed_once_with_meta_model | deleted | tests/test_single_parse.py::test_yang_expressions_parsed_once | same cache property |
| ts/test/single_parse.test.ts::reuses parsed XPath expressions across repeated validations with meta-model | deleted | ts/test/single_parse.test.ts::parses YANG XPath expressions once… | same cache property |
| ts/test/cli-stdout-flush.test.ts::matches the library schema for examples/meta-model.yang | deleted | ts/test/cli-stdout-flush.test.ts::writes a full JSON Schema larger than the pipe buffer | same >64KiB flush class |

### Conditions, choice, types

| removed check | action | retained coverage | note |
|---|---|---|---|
| `tests/test_choice_case_when.py::test_choice_when_false_skips_branch_data_ok` | migrated | `tests/cases/choice/choice-case-when:choice when false and no branch data` | |
| `tests/test_choice_case_when.py::test_choice_when_false_with_branch_data_errors` | migrated | `tests/cases/choice/choice-case-when:branch data while choice when is false` | |
| `tests/test_choice_case_when.py::test_case_when_false_with_data_errors` | migrated | `tests/cases/choice/choice-case-when:case data while case when is false` | |
| `tests/test_choice_case_when.py::test_case_b_without_case_when_when_choice_applies` | migrated | `tests/cases/choice/choice-case-when:choice when true with case b` | |
| `ts/test/choice_case_when.test.ts::accepts data when choice when is false and no branch data is provided` | migrated | `tests/cases/choice/choice-case-when:choice when false and no branch data` | |
| `ts/test/choice_case_when.test.ts::accepts data when choice when is true` | migrated | `tests/cases/choice/choice-case-when:choice when true with case b` | |
| `ts/test/choice_case_when.test.ts::rejects branch data when choice when is false` | migrated | `tests/cases/choice/choice-case-when:branch data while choice when is false` | |
| `ts/test/choice_case_when.test.ts::rejects case data when case when is false` | migrated | `tests/cases/choice/choice-case-when:case data while case when is false` | |
| `tests/test_nested_choice_under_case.py::test_outer_leaf_branch_still_validates` | migrated | `tests/cases/choice/nested-under-case:outer leaf branch` | file deleted |
| `tests/test_nested_choice_under_case.py::test_flat_inner_primitive_should_validate` | migrated | `tests/cases/choice/nested-under-case:flat inner primitive` | file deleted |
| `tests/test_nested_choice_under_case.py::test_flat_inner_other_should_validate` | migrated | `tests/cases/choice/nested-under-case:flat inner other` | file deleted |
| `tests/test_nested_choice_under_case.py::test_flat_inner_both_branches_invalid` | migrated | `tests/cases/choice/nested-under-case:both inner branches` | file deleted |
| `tests/test_nested_choice_under_case.py::test_flat_inner_and_outer_alt_invalid` | migrated | `tests/cases/choice/nested-under-case:inner and outer alt` | file deleted |
| `tests/test_nested_choice_under_case.py::test_flat_inner_primitive_and_enum_list_invalid` | migrated | `tests/cases/choice/nested-primitive-or-enum:primitive and enum list together` | file deleted |
| `ts/test/nested_choice_under_case.test.ts::outer leaf branch still validates` | migrated | `tests/cases/choice/nested-under-case:outer leaf branch` | file deleted |
| `ts/test/nested_choice_under_case.test.ts::flat inner primitive validates` | migrated | `tests/cases/choice/nested-under-case:flat inner primitive` | file deleted |
| `ts/test/nested_choice_under_case.test.ts::flat inner other validates` | migrated | `tests/cases/choice/nested-under-case:flat inner other` | file deleted |
| `ts/test/nested_choice_under_case.test.ts::both inner branches invalid` | migrated | `tests/cases/choice/nested-under-case:both inner branches` | file deleted |
| `ts/test/nested_choice_under_case.test.ts::inner and outer alt invalid` | migrated | `tests/cases/choice/nested-under-case:inner and outer alt` | file deleted |
| `ts/test/nested_choice_under_case.test.ts::primitive and enum list together invalid` | migrated | `tests/cases/choice/nested-primitive-or-enum:primitive and enum list together` | file deleted |
| `tests/test_nested_choice_with_refine.py::test_nested_choice_with_uses_refine_keeps_sibling_fields` | migrated | `tests/cases/choice/nested-with-refine:legacy type with siblings` | file deleted |
| `ts/test/nested_choice_with_refine.test.ts::nested choice + uses/refine preserves sibling leaves like name/description` | migrated | `tests/cases/choice/nested-with-refine:legacy type with siblings` | file deleted |
| `tests/test_choice_case.py::test_rfc7950_section_7_9_4_mandatory_nested_choice_enforced_when_other_case_node_exists` | migrated | `tests/cases/choice/nested-mandatory:sibling with empty inner wrap` | |
| `tests/test_choice_case.py::test_rfc7950_section_7_9_4_mandatory_nested_choice_satisfied_by_inner_branch_alone` | migrated | `tests/cases/choice/nested-mandatory:inner branch alone` | |
| `ts/test/choice_case.test.ts::enforces mandatory nested choice when outer case has sibling data` | migrated | `tests/cases/choice/nested-mandatory:sibling with empty inner wrap` | |
| `ts/test/choice_case.test.ts::accepts nested choice when inner branch alone is provided` | migrated | `tests/cases/choice/nested-mandatory:inner branch alone` | |
| `tests/test_choice_case.py::test_choice_duplicate_schema_node_name_across_cases_is_illegal` | migrated | `tests/cases/choice/duplicate-case-names` (schema_error) | |
| `ts/test/choice_case.test.ts::rejects duplicate schema node names across cases (RFC 7950 §7.9)` | migrated | `tests/cases/choice/duplicate-case-names` (schema_error) | |
| `tests/test_choice_case.py::test_mandatory_substatement_under_case_is_rejected` | migrated | `tests/cases/parser/substatements/case-mandatory` (schema_error) | |
| `ts/test/choice_case.test.ts::rejects mandatory as a direct substatement of case (Appendix A)` | migrated | `tests/cases/parser/substatements/case-mandatory` (schema_error) | |
| `ts/test/choice_case.test.ts::defaults choice mandatory to false when omitted` | deleted | `ts/test/choice_case.test.ts::parses leaf mandatory true under a case; choice stays non-mandatory` | same AST default assertion |
| `tests/test_typedef_union.py::test_typedef_union_primitive_and_composite` | migrated | `tests/cases/types/typedef-union-enums:*` | file deleted; enum-union equivalence |
| `tests/test_typedef_union.py::test_typedef_union_nested_typedefs` | merged | `tests/cases/types/typedef-union-enums:*` | same enum-typedef union path |
| `tests/test_typedef_union.py::test_typedef_union_three_members` | merged | `tests/cases/types/typedef-union-enums:*` | same enum-typedef union path |
| `tests/test_typedef_union.py::test_typedef_union_string_and_enum` | migrated | `tests/cases/types/typedef-union-pattern:*` | file deleted |
| `tests/test_typedef_union.py::test_typedef_union_empty_union` | migrated | `tests/cases/types/empty-union:any value rejected` | file deleted |
| `tests/test_typedef_union.py::test_typedef_union_in_list` | deleted | `tests/cases/types/typedef-union-enums:no member matches` | same union reject path; list context not distinct |
| `ts/test/typedef_union.test.ts::typedef union: primitive-type and composite-type enumerations` | migrated | `tests/cases/types/typedef-union-enums:*` | file deleted |
| `ts/test/typedef_union.test.ts::typedef union: nested typedefs (field-type)` | merged | `tests/cases/types/typedef-union-enums:*` | |
| `ts/test/typedef_union.test.ts::typedef union: three member typedefs` | merged | `tests/cases/types/typedef-union-enums:*` | |
| `ts/test/typedef_union.test.ts::typedef union: string pattern and enumeration` | migrated | `tests/cases/types/typedef-union-pattern:*` | |
| `ts/test/typedef_union.test.ts::typedef union: empty union rejects values` | migrated | `tests/cases/types/empty-union:any value rejected` | |
| `ts/test/typedef_union.test.ts::typedef union: used on list leaf` | deleted | `tests/cases/types/typedef-union-enums:no member matches` | |
| `tests/test_identity.py::test_validate_must_on_sibling_when_identityref_satisfies_derived_from` | migrated | `tests/cases/references/identityref-must-derived-from:derived identity satisfies must` | |
| `tests/test_identity.py::test_validate_must_on_sibling_fails_when_identityref_not_mammal_lineage` | migrated | `tests/cases/references/identityref-must-derived-from:base identity fails must` | |
| `tests/test_identity.py::test_parse_identity_module_with_must_on_sibling_leaf` | deleted | `tests/cases/references/identityref-must-derived-from` (module load) | parse covered by shared case |
| `ts/test/identity.test.ts::validate must on sibling when identityref satisfies derived-from` | migrated | `tests/cases/references/identityref-must-derived-from:derived identity satisfies must` | |
| `ts/test/identity.test.ts::validate must on sibling fails when identityref not mammal lineage` | migrated | `tests/cases/references/identityref-must-derived-from:base identity fails must` | |
| `ts/test/identity.test.ts::parses must on a leaf that constrains a sibling identityref via derived-from` | deleted | `tests/cases/references/identityref-must-derived-from` (module load) | |
| `tests/test_instance_identifier.py::test_instance_identifier_yang_valid_when_target_exists` | migrated | `tests/cases/references/instance-identifier:require-instance false allows non-path` (+ existing node) | appended to existing case |
| `tests/test_instance_identifier.py::test_instance_identifier_yang_invalid_not_absolute` | migrated | `tests/cases/references/instance-identifier:relative path rejected` | |
| `ts/test/instance_identifier.test.ts::accepts absolute path when target exists and require-instance is true` | migrated | `tests/cases/references/instance-identifier:require-instance false allows non-path` | |
| `ts/test/instance_identifier.test.ts::rejects non-absolute paths when require-instance is true` | migrated | `tests/cases/references/instance-identifier:relative path rejected` | |
| `tests/test_anydata_anyxml.py::test_validate_accepts_arbitrary_json_under_anydata_anyxml` | migrated | `tests/cases/structure/anydata-anyxml:arbitrary payloads` | |
| `tests/test_anydata_anyxml.py::test_validate_mandatory_anyxml_missing` | migrated | `tests/cases/structure/anydata-anyxml:mandatory anyxml missing` | |
| `ts/test/anydata_anyxml.test.ts::accepts arbitrary JSON payload under anydata and anyxml` | migrated | `tests/cases/structure/anydata-anyxml:arbitrary payloads` | |
| `ts/test/anydata_anyxml.test.ts::reports missing mandatory anyxml field` | migrated | `tests/cases/structure/anydata-anyxml:mandatory anyxml missing` | |
| `tests/test_list_key_uniqueness.py::test_list_key_leaf_rejects_when_and_if_feature[when ...]` | migrated | `tests/cases/structure/list-key-when` (schema_error) | file deleted |
| `tests/test_list_key_uniqueness.py::test_list_key_leaf_rejects_when_and_if_feature[if-feature ...]` | migrated | `tests/cases/structure/list-key-if-feature` (schema_error) | file deleted |
| `tests/test_list_key_uniqueness.py::test_list_key_rejects_non_existing_leaf` | migrated | `tests/cases/structure/list-key-missing` (schema_error) | file deleted |
| `ts/test/list_key_uniqueness.test.ts::rejects when ... on a list key leaf` | migrated | `tests/cases/structure/list-key-when` (schema_error) | file deleted |
| `ts/test/list_key_uniqueness.test.ts::rejects if-feature ... on a list key leaf` | migrated | `tests/cases/structure/list-key-if-feature` (schema_error) | file deleted |
| `ts/test/list_key_uniqueness.test.ts::rejects a list key that names no child leaf` | migrated | `tests/cases/structure/list-key-missing` (schema_error) | file deleted |

### Reuse, modules, parser

| removed check | action | retained coverage | note |
|---|---|---|---|
| `tests/test_grouping_uses.py::test_grouping_and_uses_basic` | migrated | `tests/cases/reuse/grouping-uses:expanded nodes` + `mandatory from nested grouping` | nested schema also covers mandatory-from-uses |
| `ts/test/grouping_uses.test.ts::basic grouping and uses validates mandatory leaf from grouping` | migrated | `tests/cases/reuse/grouping-uses:*` | same |
| `tests/test_grouping_uses.py::test_nested_grouping` | migrated | `tests/cases/reuse/grouping-uses:*` | 2-level nested uses |
| `ts/test/grouping_uses.test.ts::nested grouping (uses base inside extended)` | migrated | `tests/cases/reuse/grouping-uses:*` | same |
| `tests/test_grouping_uses.py::test_grouping_in_list` | merged | `tests/cases/reuse/grouping-uses-list:*` | same class as nested uses-in-list |
| `ts/test/grouping_uses.test.ts::uses inside list` | merged | `tests/cases/reuse/grouping-uses-list:*` | same |
| `tests/test_grouping_uses.py::test_composite_field_grouping` | migrated | `tests/cases/reuse/grouping-uses-list:*` | |
| `ts/test/grouping_uses.test.ts::composite-style nested groupings in list` | migrated | `tests/cases/reuse/grouping-uses-list:*` | |
| `tests/test_grouping_uses.py::test_must_validation_context_in_grouping` | migrated | `tests/cases/reuse/grouping-must:*` | |
| `ts/test/grouping_uses.test.ts::must in grouping uses correct sibling context` | migrated | `tests/cases/reuse/grouping-must:*` | |
| `tests/test_grouping_uses.py::test_grouping_with_refine` | merged | `tests/cases/reuse/grouping-refine-must:*` | weaker twin of refine-must |
| `ts/test/grouping_uses.test.ts::grouping with refine adds must on refined leaf` | merged | `tests/cases/reuse/grouping-refine-must:*` | |
| `tests/test_grouping_uses.py::test_must_validation_context_with_refine` | migrated | `tests/cases/reuse/grouping-refine-must:*` | |
| `ts/test/grouping_uses.test.ts::must from refine on leaf under uses` | migrated | `tests/cases/reuse/grouping-refine-must:*` | |
| `tests/test_nested_uses.py::test_parse_nested_uses_module` | deleted | `tests/cases/reuse/grouping-uses:expanded nodes` | 3-level same expansion class as 2-level |
| `ts/test/nested_uses.test.ts::parses a module with nested uses` | deleted | `tests/cases/reuse/grouping-uses:expanded nodes` | same |
| `tests/test_nested_uses.py::test_validate_data_against_nested_uses` | deleted | `tests/cases/reuse/grouping-uses:expanded nodes` | same |
| `ts/test/nested_uses.test.ts::validates instance data against nested uses expansion` | deleted | `tests/cases/reuse/grouping-uses:expanded nodes` | same |
| `tests/test_nested_uses.py::test_parse_refine_targets_list_behind_uses` | deleted | `tests/cases/reuse/refine-list-under-choice:*` | refine path via choice/case/list |
| `ts/test/nested_uses.test.ts::parses refine path over list behind nested uses` | deleted | `tests/cases/reuse/refine-list-under-choice:*` | same |
| `tests/test_nested_uses.py::test_parse_uses_cycle_through_list_raises_circular_uses` | migrated | `tests/cases/reuse/circular-uses-list-refine` (schema_error) | |
| `ts/test/nested_uses.test.ts::throws YangCircularUsesError for recursive uses through list` | migrated | `tests/cases/reuse/circular-uses-list-refine` | |
| `tests/test_circular_uses.py::test_self_referential_grouping_raises` | migrated | `tests/cases/reuse/circular-uses-self` (schema_error) | mutual cycle already in `reuse/circular-uses` |
| `ts/test/circular_uses.test.ts::raises when uses of the same grouping inside that grouping forms a cycle` | migrated | `tests/cases/reuse/circular-uses-self` | |
| `tests/test_deviation.py::test_missing_not_supported_target_is_schema_error` | migrated | `tests/cases/modules/deviation-missing-target` (schema_error) | |
| `ts/test/deviation.test.ts::reports a missing not-supported target as a schema error` | migrated | `tests/cases/modules/deviation-missing-target` | |
| `tests/test_uses_augment.py::test_uses_augment_merges_into_expanded_grouping` | deleted | `tests/cases/reuse/uses-augment:*` | AST merge implied by validation |
| `tests/test_augment.py::test_augment_same_module_merges_into_container` | deleted | `tests/cases/reuse/augment:*` | |
| `ts/test/augment.test.ts::merges same-module augment into container and validates` | deleted | `tests/cases/reuse/augment:*` | |
| `tests/test_refine.py::test_refine_bad_path_raises` | migrated | `tests/cases/reuse/refine-target-missing` (schema_error) | |
| `ts/test/refine_target_not_found.test.ts::raises when refine targets a node that does not exist in the grouping` | migrated | `tests/cases/reuse/refine-target-missing` | file removed |
| `tests/test_refine.py::test_refine_min_elements_bad_path_raises` | migrated | `tests/cases/reuse/refine-target-missing-path` (schema_error) | |
| `ts/test/refine_target_not_found.test.ts::raises when refine path targets missing list node` | migrated | `tests/cases/reuse/refine-target-missing-path` | file removed |
| `tests/test_refine.py::test_refine_applies_max_min_elements_to_list` | migrated | `tests/cases/reuse/refine-list-cardinality:*` | AST max/min → instance min/max-elements |
| `ts/test/refine_list.test.ts::refine applies max/min-elements to list after expansion` | migrated | `tests/cases/reuse/refine-list-cardinality:*` | |
| `tests/test_refine.py::test_refine_applies_to_list_under_choice_case` | migrated | `tests/cases/reuse/refine-list-under-choice:*` | |
| `ts/test/refine_list.test.ts::refine path through choice/case reaches the list` | migrated | `tests/cases/reuse/refine-list-under-choice:*` | |
| `tests/test_refine.py::test_uses_inside_list_with_refine_applies_to_grouping_leaf` | migrated | `tests/cases/reuse/uses-in-list-refine-must:*` | |
| `ts/test/refine_list.test.ts::uses inside list with refine applies must to grouping leaf` | migrated | `tests/cases/reuse/uses-in-list-refine-must:*` | |
| `tests/test_refine.py::test_grouping_generic_field_without_case_array_raises_circular_uses_when_expanding` | migrated | `tests/cases/reuse/circular-uses-generic-field` (schema_error) | |
| `ts/test/refine_list.test.ts::recursive uses generic-field under list fields throws when expanding` | migrated | `tests/cases/reuse/circular-uses-generic-field` | |
| `tests/test_refine.py::test_refine_mandatory_false_on_grouping_leaf` | migrated | `tests/cases/reuse/refine-mandatory-false:leaf omitted` | |
| `ts/test/refine_mandatory.test.ts::refine mandatory false overrides grouping leaf mandatory true after uses expand` | migrated | `tests/cases/reuse/refine-mandatory-false:leaf omitted` | file removed |
| `ts/test/imported_grouping.test.ts::expands uses prefix:grouping from an imported module` | deleted | `tests/cases/modules/import:*` | basic imported grouping+typedef already covered |
| `tests/test_pattern_constraint_metadata.py::test_validate_uses_pattern_error_message_and_app_tag` | migrated | `tests/cases/types/pattern-error-metadata:*` | message includes error-app-tag |
| `ts/test/pattern_constraint_metadata.test.ts::validate uses pattern error-message and error-app-tag` | migrated | `tests/cases/types/pattern-error-metadata:*` | |
| `tests/test_basic.py::test_parse_ordered_by_accepted_on_list_and_leaf_list` | migrated | `tests/cases/parser/arguments/ordered-by:list and leaf-list` | |
| `ts/test/basic.test.ts::accepts ordered-by on list and leaf-list` | migrated | `tests/cases/parser/arguments/ordered-by:list and leaf-list` | |
| `tests/test_unsupported_skip.py::test_module_rejects_top_level_input_output[input]` | migrated | `tests/cases/parser/arguments/top-level-input` (schema_error) | |
| `ts/test/unsupported_skip.test.ts::rejects top-level input` | migrated | `tests/cases/parser/arguments/top-level-input` | |
| `tests/test_unsupported_skip.py::test_module_rejects_top_level_input_output[output]` | migrated | `tests/cases/parser/arguments/top-level-output` (schema_error) | |
| `ts/test/unsupported_skip.test.ts::rejects top-level output` | migrated | `tests/cases/parser/arguments/top-level-output` | |
| `tests/test_unsupported_skip.py::test_container_rejects_rpc` | migrated | `tests/cases/parser/substatements/container-rpc` (schema_error) | |
| `ts/test/unsupported_skip.test.ts::rejects rpc inside container` | migrated | `tests/cases/parser/substatements/container-rpc` | |

### JSON Schema, examples, tooling

| removed check | action | retained coverage | note |
|---|---|---|---|
| `tests/json/test_rpc_json.py::test_schema_to_yang_json_includes_rpcs` | deleted | `tests/json/test_rpc_json.py::test_rpc_emitted_under_x_yang_rpcs_and_round_trips` (+ `tests/json/test_generator.py::test_schema_to_yang_json_writes_file` for file write) | same rpc schema content; file-write API already covered |
| `ts/test/json/generator.test.ts::round-trips if-features metadata on leaf` | deleted | `ts/test/json/if_features_json.test.ts::emits leaf if-features and round-trips through parseJsonSchema` | exact duplicate of dedicated if-features test |
