---
description: Protobuf/buf rules — lint before format before generate, no field number reuse, ConnectRPC health checking, cursor pagination
globs: "**/*.proto, **/buf.yaml, **/buf.gen.yaml, **/buf.lock"
alwaysApply: false
paths:
  - "**/*.proto"
  - "**/buf.yaml"
  - "**/buf.gen.yaml"
  - "**/buf.lock"
---

# Protobuf

## Buf Pipeline
- `buf format` must always call `buf lint` first
- `buf generate` must always call `buf format` first (which calls `buf lint`)
- `buf breaking` must always run when `buf generate` runs
- The full chain for any code generation is: `buf lint` → `buf format` → `buf breaking` → `buf generate`
- Fix all lint warnings before committing — don't suppress with comments

## Schema Design
- Never reuse or change field numbers — deleted fields must be `reserved`
- Use `google.protobuf.Timestamp` for time fields, not int64/string
- Use `google.protobuf.FieldMask` for partial updates
- Enum values must have a `_UNSPECIFIED = 0` default

## Connect/gRPC Services
- Use ConnectRPC for all service definitions
- IMPORTANT: All ConnectRPC services must implement health checking for Kubernetes (`grpc.health.v1.Health`) — every service must respond to liveness and readiness probes
- Include application-specific error codes in error details alongside standard Connect error codes
- List RPCs must always be server-streaming — never unary
- Use cursor-based pagination for list endpoints: `page_size` + `page_token` / `next_page_token` (AIP-158 style)
- Every list RPC should accept `page_size` (default 50, max 1000) and return `next_page_token`

## Naming
- Services: `PascalCase` (e.g. `UserService`)
- RPCs: `PascalCase` verbs (e.g. `CreateUser`, `ListUsers`)
- Messages: `PascalCase` (e.g. `CreateUserRequest`, `CreateUserResponse`)
- Fields: `snake_case`
- Enums: `UPPER_SNAKE_CASE` with type prefix (e.g. `STATUS_ACTIVE`)