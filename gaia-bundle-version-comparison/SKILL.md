---
name: gaia-bundle-version-comparison
description: Use when asked to compare site-level Gaia bundle_version values in deployconf.staging.xml and deployconf.literatum.xml, identify product-version mismatches or missing Gaia configuration, or create a comparison table or CSV report.
---

# Gaia Bundle Version Comparison

Use this workflow for a read-only comparison of product-level Gaia bundle versions between staging and literatum.

## Workflow

1. Treat a request to create the report as authorization to read the two named configs and write the requested output; do not pause for redundant approval. Default inputs are `~/sourcegit/deployconf/deployconf.staging.xml` and `~/sourcegit/deployconf/deployconf.literatum.xml`.
2. Compare only `<gaia bundle_version="…">` directly inside each `<product name="…">`. Ignore the top-level Gaia cluster configuration. Include the union of product names from both files; honor `-p product1,product2` when the user requests a subset.
3. Prefer `~/checkGaia.sh`, which delegates to `~/sourcegit/deployconf/scripts/compare_gaia_bundle_versions.py`. Check that the helper, utility, and input files exist before running them. Use `-o <absolute-path>.csv` for CSV; otherwise the helper prints a table. If the helper is unavailable, generate the same report with a temporary Python standard-library XML/CSV script in session-local storage; do not add or modify repository files.
4. If the user did not specify an output destination, write `gaia_bundle_version_comparison.csv` under the active session's `files/` directory when available; otherwise use `~/gaia_bundle_version_comparison.csv`. Report the full absolute path.
5. Verify the CSV has `site,staging_bundle_version,literatum_bundle_version,status` columns, sorted site rows, and only these statuses: `MATCH`, `DIFFERENT`, `STAGING_ONLY`, `LITERATUM_ONLY`, `MISSING_BOTH`. Missing versions are empty cells. Validate row counts and status distribution from the generated data; never assume they remain constant between runs.

## Scope and errors

- Do not edit either deployconf XML file, the helper, or the comparison utility while generating a report.
- Do not commit, push, merge, or deploy as part of this workflow.
- If an input is missing, unreadable, or malformed, stop and report the exact error; do not present a partial report as complete.
- If report generation or validation fails, state that plainly and identify the output path only if a valid report was actually written.
