FROM node:22-bookworm-slim AS web
WORKDIR /src/apps/web
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build
FROM golang:1.27.3-bookworm AS gateway
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY cmd cmd
COPY internal internal
RUN mkdir /data && chown 65532:65532 /data
RUN CGO_ENABLED=0 go build -trimpath -o /pulse ./cmd/gateway
FROM gcr.io/distroless/static-debian12:nonroot
WORKDIR /app
COPY --from=gateway /pulse /pulse
COPY --from=gateway --chown=65532:65532 /data /data
COPY --from=web /src/apps/web/dist /app/apps/web/dist
ENV PORT=8081 PULSE_DATA=/data
EXPOSE 8081
ENTRYPOINT ["/pulse"]
