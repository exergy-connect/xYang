"""Run cross-entity FK test with DEBUG logging and print path cache stats."""
import logging
import sys
from pathlib import Path

# Enable DEBUG for xyang before importing
logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")
for name in ("xyang.validator", "xyang.xpath.evaluator"):
    logging.getLogger(name).setLevel(logging.DEBUG)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
from xyang import YangValidator, parse_yang_file

def main():
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    meta_model = parse_yang_file(str(yang_path))
    validator = YangValidator(meta_model)

    data = {
        "data-model": {
            "name": "M",
            "version": "1.0",
            "author": "A",
            "consolidated": True,
            "entities": [
                {
                    "name": "property_detail",
                    "primary_key": "mls_number",
                    "fields": [
                        {"name": "mls_number", "type": "integer"},
                        {"name": "sqft", "type": "integer"},
                    ],
                },
                {
                    "name": "property_economics",
                    "primary_key": "mls_number",
                    "fields": [
                        {"name": "mls_number", "type": "integer", "foreignKeys": [{"entity": "property_detail"}]},
                        {"name": "price", "type": "integer"},
                        {
                            "name": "price_per_sqft",
                            "type": "number",
                            "computed": {
                                "operation": "division",
                                "fields": [
                                    {"field": "price"},
                                    {"field": "sqft", "entity": "property_detail"},
                                ],
                            },
                        },
                    ],
                },
            ],
        }
    }

    is_valid, errors, _ = validator.validate(data)
    stats = validator._doc_validator._evaluator.get_cache_stats()

    print("\n" + "=" * 60)
    print("Validation result:", "VALID" if is_valid else "INVALID")
    print("Errors:", len(errors))
    for e in errors:
        print("  -", e)
    print("=" * 60)
    print("Path cache stats:", stats)
    print("=" * 60)

if __name__ == "__main__":
    main()
