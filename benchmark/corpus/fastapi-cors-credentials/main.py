"""Fixture: CORS wildcard+credentials (seeded) + explicit-origin control."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
# SEEDED BUG [FCORS-1]: wildcard origins WITH credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
)

safe = FastAPI()
# CLEAN CONTROL: explicit origin list — must NOT be flagged.
safe.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.example.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
)
