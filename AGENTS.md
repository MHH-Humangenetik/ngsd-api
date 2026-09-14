# AGENTS.md

## Releasing

There is no CI. A release is manual and has two halves — **both are required**.
Tagging git alone does not make the package installable; consumers resolve it
from the GitLab PyPI index, not from git.

1. Bump `version` in `pyproject.toml` via `uv version <new>`, refreshing `uv.lock`.
   Commit as its own `🔖 release: bump version to X.Y.Z` commit.
2. Tag and push: `git tag vX.Y.Z && git push origin main && git push origin vX.Y.Z`.
3. Build and upload to the registry:

   ```bash
   uv build
   UV_PUBLISH_USERNAME='gitlab+deploy-token-<n>' \
   UV_PUBLISH_PASSWORD='<deploy token>' \
   UV_PUBLISH_URL='https://gitlab.mh-hannover.local/api/v4/projects/272/packages/pypi' \
   uv publish dist/ngsd_api-X.Y.Z*
   ```

4. Verify it actually landed before telling anyone it shipped:

   ```bash
   curl -s -u '<user>:<token>' \
     https://gitlab.mh-hannover.local/api/v4/projects/272/packages/pypi/simple/ngsd-api/
   ```

Credentials are a GitLab deploy token with `write_package_registry` scope
(Settings → Repository → Deploy tokens on project 272). Do not commit the
token or paste it into a command that lands in shell history — source it from
a gitignored `.env` or the keychain.

An index named `MHH_GitLab` appears in older shell history as `uv publish
--index=MHH_GitLab`. That index is not defined anywhere in this repo or in
`~/.config/uv/`; `UV_PUBLISH_URL` is what actually routes the upload. Omit the
flag.

Consumers (e.g. `revio-ngsd`) pin `ngsd-api` from this index and need a
released version — pushing a tag does not unblock them.
