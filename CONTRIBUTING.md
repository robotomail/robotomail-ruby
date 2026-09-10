# Contributing

Run the development checks in README.md before submitting a change. Use the local HTTP fixture; never commit API keys or account data. Endpoint/model changes should start with the pinned public OpenAPI contract and regeneration. Add regression tests for behavior changes.

## Releases

1. Update the version in the package manifest, `sdk.json`, user-agent string and any exported version constant. Update the README installation tag.
2. Run tests, generation checks, and the package build. Review the package file list for SDK-only contents.
3. Commit and push, then create an annotated `vVERSION` tag on that commit. GitHub release tags must match the package version.
4. Use the manual Publish workflow, providing that exact tag. Configure the registry credential or trusted publisher first. The workflow checks out that tag, reruns tests and builds before publishing.

The initial source release is `v0.1.0`. Registry credentials are never included in this repository. GitHub checks may require Actions spending to be enabled; local test commands are the same checks.
