from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Hello World API")


class HealthResponse(BaseModel):
    status: str


class HelloResponse(BaseModel):
    message: str


@app.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(status="ok")


@app.get("/hello/{name}", response_model=HelloResponse)
def hello_name(name: str):
    return HelloResponse(message=f"Hello, {name}!")