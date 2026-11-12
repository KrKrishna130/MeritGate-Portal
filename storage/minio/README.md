# Local MinIO source build

This image compiles the official community source at the pinned release
`RELEASE.2025-10-15T17-29-55Z`. It avoids the prebuilt
`quay.io/minio/minio` / `minio/minio` image repositories.

The source and its AGPLv3 license are at:
https://github.com/minio/minio/tree/RELEASE.2025-10-15T17-29-55Z

Official source-build instructions:
https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z

Run from the project root:

```bash
docker compose build minio
docker compose up --build -d
```

The first build requires access to Docker Hub for Go/Alpine base images and to
the Go module proxy/checksum database and GitHub as needed. It can take several
minutes, especially on an older Intel Mac. Go is installed only inside the build
container; no host Go installation is needed. GOAMD64=v1 targets older x86 CPUs.

This changes only how the service image is obtained. The service name, ports,
credentials, bucket and `minio_data` volume are preserved. Console features vary
by community release; this source release provides an object browser rather than
the older full administrator console. The app creates its report bucket on export.

The community repository is archived and no longer maintained. This source build
is a local development workaround, not a claim of current security support. For
production, evaluate a maintained storage distribution/service separately.

If you see an error during `go install`, share the failed build step and its final
error lines. Do not change `.env` or erase volumes to resolve a registry pull error.
