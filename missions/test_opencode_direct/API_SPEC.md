# API Specification — test_opencode_direct "Hello World API"

## OpenAPI 3.0 Specification

```yaml
openapi: 3.0.3
info:
  title: Hello World API
  description: Minimal FastAPI service to verify the Cressida pipeline works end-to-end.
  version: 1.0.0
paths:
  /health:
    get:
      operationId: health
      summary: Health check
      description: Returns service health status. Use to verify the service is running.
      tags:
        - health
      responses:
        "200":
          description: Service is healthy
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/HealthResponse"
              example:
                status: "ok"
  /hello/{name}:
    get:
      operationId: hello
      summary: Personalized greeting
      description: Returns a greeting message with the provided name.
      tags:
        - greeting
      parameters:
        - name: name
          in: path
          required: true
          description: Name to include in greeting
          schema:
            type: string
            minLength: 1
          example: "World"
      responses:
        "200":
          description: Successful greeting
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/HelloResponse"
              example:
                message: "Hello, World!"
components:
  schemas:
    HealthResponse:
      type: object
      required:
        - status
      properties:
        status:
          type: string
          description: Service health status
          enum:
            - "ok"
    HelloResponse:
      type: object
      required:
        - message
      properties:
        message:
          type: string
          description: Personalized greeting message
tags:
  - name: health
    description: Health check endpoints
  - name: greeting
    description: Greeting endpoints
```

## Endpoints Summary

| Method | Path | Parameters | Response Model | Status |
|---|---|---|---|---|
| GET | `/health` | None | `HealthResponse` | Stable |
| GET | `/hello/{name}` | `name` (path, string) | `HelloResponse` | Stable |

## Response Examples

### GET /health

```json
{
  "status": "ok"
}
```

### GET /hello/World

```json
{
  "message": "Hello, World!"
}
```

### GET /hello/Alice

```json
{
  "message": "Hello, Alice!"
}
```

## Error Responses

No error responses are defined for this smoke test. All requests return 200 with valid responses.

## Implementation Notes

1. **Automatic OpenAPI docs:** FastAPI generates `/docs` (Swagger UI) and `/redoc` (ReDoc) automatically
2. **Response validation:** Pydantic models enforce response structure at code level
3. **Content-Type:** All responses use `application/json`
4. **Encoding:** UTF-8 (default for JSON)
