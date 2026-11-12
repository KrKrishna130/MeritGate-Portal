# Build the official community source instead of pulling an unavailable MinIO image.
FROM golang:1.25-alpine AS builder
ARG MINIO_VERSION=RELEASE.2025-10-15T17-29-55Z
ENV CGO_ENABLED=0
ENV GOAMD64=v1
RUN apk add --no-cache ca-certificates git
RUN GOBIN=/out go install -v github.com/minio/minio@${MINIO_VERSION}

FROM alpine:3.22
RUN apk add --no-cache ca-certificates tzdata && mkdir -p /data
COPY --from=builder /out/minio /usr/local/bin/minio
EXPOSE 9000 9001
VOLUME ["/data"]
ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]
